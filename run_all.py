"""Single entry point: raw NSE files to the compiled research paper.

    python run_all.py                     everything, every configured session
    python run_all.py --date 27012022     one session through the per-session stages
    python run_all.py --stage report      one stage
    python run_all.py --force             redo work already on disk

Two things shape how this is ordered.

*Per-session, not per-stage.* Parsing, enrichment and book reconstruction all run for one
session before the next session starts. Enrichment reads what the parse just wrote and the
book replay reads it again, so keeping them together means the second and third readers hit
the page cache instead of the disk. Running stage 1 across all twenty-four sessions first
would evict every one of those files before stage 2 asked for them - on a 133 GB corpus
that is the difference between a cached read and a cold one, twice per session. The
analysis stages come after, because each of them aggregates across sessions and cannot
start until all of them exist.

*Resumable at session granularity.* Every per-session stage checks its own output before
doing any work, so an interrupted run continues rather than restarting. `--force` redoes a
session whose inputs changed.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS
from utils.logger import setup_logger
from utils.progress import Elapsed

logger = setup_logger("Pipeline", "pipeline.log")

# Stage 1, 2 and 4 run once per session; the rest run once over everything.
PER_SESSION_STAGES = ["parse", "enrich", "clob"]
AGGREGATE_STAGES = ["analyze", "clob-analyze", "insights", "bloomberg", "report"]
ALL_STAGES = PER_SESSION_STAGES + AGGREGATE_STAGES


@dataclass
class Outcome:
    """What each stage did, so the run ends with a report rather than a scrollback."""

    name: str
    seconds: float = 0.0
    failures: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _run(name: str, fn: Callable[[], None], outcomes: List[Outcome]) -> Outcome:
    """Run one stage, recording rather than raising so later stages still get their turn.

    KeyboardInterrupt is deliberately not caught here: stopping the run is the one thing the
    operator asked for, and swallowing it into a stage failure would continue to the next
    stage instead.
    """
    outcome = Outcome(name)
    elapsed = Elapsed()
    try:
        fn()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        outcome.failures.append(f"{type(exc).__name__}: {exc}")
        logger.error(f"[FAILED] {name}: {exc}")
        logger.debug(traceback.format_exc())
    outcome.seconds = elapsed.secs
    outcomes.append(outcome)
    return outcome


def _print_summary(outcomes: List[Outcome], total: float) -> int:
    width = max((len(o.name) for o in outcomes), default=10)
    logger.info("=" * (width + 34))
    logger.info(f"{'stage'.ljust(width)}  {'elapsed':>10}  status")
    logger.info("-" * (width + 34))
    for o in outcomes:
        seconds = f"{o.seconds:.1f}s" if o.seconds < 90 else f"{o.seconds / 60:.1f}m"
        logger.info(f"{o.name.ljust(width)}  {seconds:>10}  {'ok' if o.ok else 'FAILED'}")
    logger.info("=" * (width + 34))
    logger.info(f"total {total / 60:.1f} min")

    failed = [o for o in outcomes if not o.ok]
    for o in failed:
        for message in o.failures:
            logger.error(f"  {o.name}: {message}")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="NSE expiry-day VWAP microstructure pipeline, end to end",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--stage", choices=[*ALL_STAGES, "all"], default="all",
                        help="run a single stage instead of the whole pipeline")
    parser.add_argument("--date", help="single session, DDMMYYYY (per-session stages only)")
    parser.add_argument("--symbol", help="single symbol (book reconstruction only)")
    parser.add_argument("--force", action="store_true",
                        help="redo stages whose output already exists")
    parser.add_argument("--parse-all-eq", action="store_true",
                        help="parse every EQ symbol, not just TARGET_SYMBOLS (much larger output)")
    parser.add_argument("--all-symbols", action="store_true",
                        help="enrich every parsed symbol, not just TARGET_SYMBOLS")
    args = parser.parse_args(argv)

    # Imported here, not at module scope: several of these load DuckDB, matplotlib and
    # statsmodels, which together cost seconds that `--help` and a bad argument should not.
    from stage1_parse.tick_parser import parse_session
    from stage2_enrich.enricher import run_enrich
    from stage3_analysis.run_all_analysis import run_analysis
    from stage4_clob.clob_builder import build_clob_for_session
    from stage5_clob_analysis.run_clob_analysis import run_clob_analysis
    from stage6_insights.run_insights import run_insights
    from stage7_bloomberg.run_bloomberg_analysis import run_bloomberg
    from stage8_report.generate_report import generate_report

    wanted = ALL_STAGES if args.stage == "all" else [args.stage]
    sessions = [args.date] if args.date else ALL_TARGET_DATES
    parse_symbols = None if args.parse_all_eq else TARGET_SYMBOLS
    enrich_symbols = [] if args.all_symbols else None
    book_symbols = [args.symbol] if args.symbol else None

    outcomes: List[Outcome] = []
    started = time.time()

    try:
        per_session = [s for s in PER_SESSION_STAGES if s in wanted]
        if per_session:
            logger.info(f"=== per-session stages {per_session} over {len(sessions)} sessions ===")
            for index, session in enumerate(sessions, 1):
                logger.info(f"--- [{index:02d}/{len(sessions):02d}] session {session} ---")
                if "parse" in wanted:
                    _run(f"parse {session}",
                         lambda s=session: parse_session(s, symbols=parse_symbols, force=args.force),
                         outcomes)
                if "enrich" in wanted:
                    _run(f"enrich {session}",
                         lambda s=session: run_enrich(single_date=s, symbols=enrich_symbols,
                                                      force=args.force),
                         outcomes)
                if "clob" in wanted:
                    _run(f"clob {session}",
                         lambda s=session: build_clob_for_session(s, symbols=book_symbols,
                                                                  force=args.force),
                         outcomes)

        for name, fn in (("analyze", run_analysis),
                         ("clob-analyze", run_clob_analysis),
                         ("insights", run_insights),
                         ("bloomberg", run_bloomberg),
                         ("report", generate_report)):
            if name in wanted:
                logger.info(f"=== {name} ===")
                _run(name, fn, outcomes)

    except KeyboardInterrupt:
        logger.warning("[ABORTED] interrupted; stages already finished are on disk and "
                       "will be skipped on the next run")
        _print_summary(outcomes, time.time() - started)
        return 130

    return _print_summary(outcomes, time.time() - started)


if __name__ == "__main__":
    raise SystemExit(main())
