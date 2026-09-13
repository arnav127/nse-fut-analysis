"""Single entry point: raw NSE files to the compiled report.

    python run_all.py                      everything, every configured session
    python run_all.py --jobs 4             four sessions at a time
    python run_all.py --date 27012022      one session through the per-session stages
    python run_all.py --stage report       one stage
    python run_all.py --force              redo work already on disk

Three things shape how this is ordered.

*Per-session, not per-stage.* Parsing, enrichment and book reconstruction all run for one
session before the next session starts. Enrichment reads what the parse just wrote and the
book replay reads it again, so keeping them together means the later readers hit the page
cache instead of the disk. Running stage 1 across every session first would evict all of it
before stage 2 asked. The analysis stages come afterwards, because each aggregates across
sessions and cannot start until they all exist.

*Sessions in parallel.* They are independent, so `--jobs` runs several at once. The budget is
divided among the workers rather than left to each of them: nsetick and DuckDB both size
themselves from the machine, so four workers each helping themselves to a quarter of memory
is the whole of it - and on a cluster the machine is not the allocation. See utils/resources.

*Resumable at session granularity.* Every per-session stage checks its own output before
doing any work, so an interrupted run continues rather than restarting. `--force` redoes a
session whose inputs changed.
"""

from __future__ import annotations

import argparse
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional, Sequence

from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS
from utils.logger import setup_logger
from utils.progress import Elapsed
from utils.resources import describe, suggested_jobs, worker_budget

logger = setup_logger("Pipeline", "pipeline.log")

# Stages 1, 2 and 4 run once per session; the rest run once over everything.
PER_SESSION_STAGES = ["parse", "enrich", "clob"]
AGGREGATE_STAGES = ["analyze", "clob-analyze", "insights", "bloomberg", "report"]
ALL_STAGES = PER_SESSION_STAGES + AGGREGATE_STAGES

# The universe builder ranks securities on turnover, trade counts and price level, all of
# which come from the trade tape. Scanning the whole cross-section for orders as well costs
# roughly a hundred gigabytes for data nothing reads.
UNIVERSE_SCAN_CATEGORIES = ("cash_trades",)


@dataclass
class Outcome:
    """What each unit of work did, so the run ends with a report rather than a scrollback."""

    name: str
    seconds: float = 0.0
    failures: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class SessionPlan:
    """Everything a worker needs. Picklable, because it crosses a process boundary."""

    session: str
    stages: Sequence[str]
    parse_symbols: Optional[List[str]]
    enrich_symbols: Optional[List[str]]
    book_symbols: Optional[List[str]]
    categories: Optional[Sequence[str]]
    force: bool
    memory_mb: int
    threads: int


def run_one_session(plan: SessionPlan) -> Outcome:
    """Parse, enrich and rebuild books for one session.

    Top-level rather than a closure because a process pool has to pickle it. The stage
    imports are inside so a worker pays only for what it runs, and so `--help` does not load
    DuckDB and matplotlib.
    """
    from stage1_parse.tick_parser import parse_session
    from stage2_enrich.enricher import run_enrich
    from stage4_clob.clob_builder import build_clob_for_session

    outcome = Outcome(f"session {plan.session}")
    elapsed = Elapsed()
    steps = [
        ("parse", lambda: parse_session(
            plan.session, symbols=plan.parse_symbols, force=plan.force,
            categories=plan.categories, threads=plan.threads,
            memory_limit_mb=plan.memory_mb)),
        ("enrich", lambda: run_enrich(
            single_date=plan.session, symbols=plan.enrich_symbols, force=plan.force,
            memory_limit_mb=plan.memory_mb, threads=plan.threads)),
        ("clob", lambda: build_clob_for_session(
            plan.session, symbols=plan.book_symbols, force=plan.force,
            memory_limit_mb=plan.memory_mb, threads=plan.threads)),
    ]
    for name, function in steps:
        if name not in plan.stages:
            continue
        try:
            function()
        except Exception as exc:
            outcome.failures.append(f"{name}: {type(exc).__name__}: {exc}")
            logger.error(f"[FAILED] {name} {plan.session}: {exc}")
            logger.debug(traceback.format_exc())
    outcome.seconds = elapsed.secs
    return outcome


def _run(name: str, function: Callable[[], None], outcomes: List[Outcome]) -> None:
    """Run one aggregate stage, recording rather than raising so later stages still run.

    KeyboardInterrupt is deliberately not caught: stopping the run is the one thing the
    operator asked for, and folding it into a stage failure would continue to the next stage.
    """
    outcome = Outcome(name)
    elapsed = Elapsed()
    try:
        function()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        outcome.failures.append(f"{type(exc).__name__}: {exc}")
        logger.error(f"[FAILED] {name}: {exc}")
        logger.debug(traceback.format_exc())
    outcome.seconds = elapsed.secs
    outcomes.append(outcome)


def _summary(outcomes: List[Outcome], total: float) -> int:
    width = max((len(o.name) for o in outcomes), default=10)
    logger.info("=" * (width + 34))
    logger.info(f"{'stage'.ljust(width)}  {'elapsed':>10}  status")
    logger.info("-" * (width + 34))
    for outcome in outcomes:
        seconds = (f"{outcome.seconds:.1f}s" if outcome.seconds < 90
                   else f"{outcome.seconds / 60:.1f}m")
        logger.info(f"{outcome.name.ljust(width)}  {seconds:>10}  "
                    f"{'ok' if outcome.ok else 'FAILED'}")
    logger.info("=" * (width + 34))
    logger.info(f"total {total / 60:.1f} min")

    failed = [o for o in outcomes if not o.ok]
    for outcome in failed:
        for message in outcome.failures:
            logger.error(f"  {outcome.name}: {message}")
    return 1 if failed else 0


def _per_session(plans: List[SessionPlan], jobs: int, outcomes: List[Outcome]) -> None:
    if jobs <= 1:
        for index, plan in enumerate(plans, 1):
            logger.info(f"--- [{index:02d}/{len(plans):02d}] session {plan.session} ---")
            outcomes.append(run_one_session(plan))
        return

    logger.info(f"--- {len(plans)} sessions, {jobs} at a time ---")
    # Workers append to the same log file. Records from different sessions interleave, but
    # each record is a single write and stays intact; every message carries its session, so
    # the result is still readable.
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_one_session, plan): plan for plan in plans}
        for done, future in enumerate(as_completed(futures), 1):
            plan = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                # A worker that died rather than returned - an out-of-memory kill, most
                # likely. Recorded against the session so the summary names it.
                outcome = Outcome(f"session {plan.session}",
                                  failures=[f"worker died: {type(exc).__name__}: {exc}"])
            outcomes.append(outcome)
            logger.info(f"[{done:02d}/{len(plans):02d}] session {plan.session} "
                        f"{'ok' if outcome.ok else 'FAILED'} in {outcome.seconds:.0f}s")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="NSE expiry-day microstructure pipeline, end to end",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--stage", choices=[*ALL_STAGES, "all"], default="all",
                        help="run a single stage instead of the whole pipeline")
    parser.add_argument("--date", help="single session, DDMMYYYY (per-session stages only)")
    parser.add_argument("--symbol", help="single symbol (book reconstruction only)")
    parser.add_argument("--force", action="store_true",
                        help="redo stages whose output already exists")
    parser.add_argument("--jobs", type=int, default=1,
                        help="sessions to process concurrently; the memory and thread budget "
                             "is divided among them")
    parser.add_argument("--universe-scan", action="store_true",
                        help="parse the whole EQ cross-section, trades only, so "
                             "scripts/build_universe.py can rank securities")
    parser.add_argument("--all-symbols", action="store_true",
                        help="enrich every parsed symbol, not just the study universe")
    args = parser.parse_args(argv)

    memory_mb, threads = worker_budget(args.jobs)
    logger.info(f"=== resources: {describe()} ===")
    logger.info(f"=== {args.jobs} job(s), {memory_mb / 1024:.1f} GiB and {threads} threads "
                f"each (suggested --jobs {suggested_jobs()}) ===")

    wanted = ALL_STAGES if args.stage == "all" else [args.stage]
    sessions = [args.date] if args.date else ALL_TARGET_DATES

    plans = [
        SessionPlan(
            session=session,
            # A universe scan has nothing to enrich or replay: the universe it would narrow
            # to does not exist until the builder has run.
            stages=(("parse",) if args.universe_scan
                    else tuple(s for s in PER_SESSION_STAGES if s in wanted)),
            parse_symbols=None if args.universe_scan else TARGET_SYMBOLS,
            enrich_symbols=[] if args.all_symbols else None,
            book_symbols=[args.symbol] if args.symbol else None,
            categories=UNIVERSE_SCAN_CATEGORIES if args.universe_scan else None,
            force=args.force,
            memory_mb=memory_mb,
            threads=threads,
        )
        for session in sessions
    ]

    outcomes: List[Outcome] = []
    started = time.time()

    try:
        if args.universe_scan or any(stage in wanted for stage in PER_SESSION_STAGES):
            _per_session(plans, args.jobs, outcomes)

        if args.universe_scan:
            logger.info("[NEXT] run scripts/build_universe.py, then rerun without "
                        "--universe-scan to parse the selected universe")
            return _summary(outcomes, time.time() - started)

        from stage3_analysis.run_all_analysis import run_analysis
        from stage5_clob_analysis.run_clob_analysis import run_clob_analysis
        from stage6_insights.run_insights import run_insights
        from stage7_bloomberg.run_bloomberg_analysis import run_bloomberg
        from stage8_report.generate_report import generate_report

        for name, function in (("analyze", run_analysis),
                               ("clob-analyze", run_clob_analysis),
                               ("insights", run_insights),
                               ("bloomberg", run_bloomberg),
                               ("report", generate_report)):
            if name in wanted:
                logger.info(f"=== {name} ===")
                _run(name, function, outcomes)

    except KeyboardInterrupt:
        logger.warning("[ABORTED] interrupted; finished sessions are on disk and will be "
                       "skipped on the next run")
        _summary(outcomes, time.time() - started)
        return 130

    return _summary(outcomes, time.time() - started)


if __name__ == "__main__":
    raise SystemExit(main())
