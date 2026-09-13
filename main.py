"""Single entry point for the NSE expiry-day VWAP microstructure pipeline.

    python main.py                      # every stage, every configured session
    python main.py --stage parse        # one stage
    python main.py --date 27012022      # one session through the data stages
    python main.py --force              # redo work already on disk

Stages 1, 2 and 4 are resumable: each checks for its own output before doing anything, so a
run that was interrupted picks up where it stopped. `--force` is the way to redo a session
whose inputs changed; deleting the directory works too.
"""

from __future__ import annotations

import argparse
import sys
import time

from stage1_parse.run_parse_all import run_parse
from stage2_enrich.run_enrich_all import run_enrich
from stage3_analysis.run_all_analysis import run_analysis
from stage4_clob.run_clob_all import run_clob
from stage5_clob_analysis.run_clob_analysis import run_clob_analysis
from stage6_bloomberg.run_bloomberg_analysis import run_bloomberg
from stage7_report.generate_report import generate_report
from utils.logger import setup_logger

logger = setup_logger("Pipeline", "pipeline.log")

STAGES = ["parse", "enrich", "clob", "analyze", "clob-analyze", "bloomberg", "report"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NSE expiry-day VWAP microstructure pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--stage", choices=[*STAGES, "all"], default="all",
                        help="run a single stage instead of the whole pipeline")
    parser.add_argument("--date", help="single session, DDMMYYYY (data stages only)")
    parser.add_argument("--symbol", help="single symbol (CLOB stage only)")
    parser.add_argument("--force", action="store_true",
                        help="redo stages whose output already exists")
    parser.add_argument("--all-symbols", action="store_true",
                        help="enrich the whole EQ cross-section, not just TARGET_SYMBOLS")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    wanted = STAGES if args.stage == "all" else [args.stage]

    # Ordered so the data stages run before anything that reads their output. The CLOB
    # replay depends on stage 1 only - it reads the parsed orders, not the enriched ones -
    # but it is sequenced after enrichment so a single-machine run does one heavy job at a
    # time rather than competing for the same cores and disk.
    steps = [
        ("parse", "parse", lambda: run_parse(single_date=args.date, force=args.force)),
        ("enrich", "enrich", lambda: run_enrich(
            single_date=args.date,
            symbols=[] if args.all_symbols else None,
            force=args.force,
        )),
        ("clob", "CLOB replay", lambda: run_clob(
            single_date=args.date, single_symbol=args.symbol, force=args.force)),
        ("analyze", "trade analysis", run_analysis),
        ("clob-analyze", "CLOB analysis", run_clob_analysis),
        ("bloomberg", "Bloomberg analysis", run_bloomberg),
        ("report", "report", generate_report),
    ]

    started = time.time()
    try:
        for key, label, fn in steps:
            if key not in wanted:
                continue
            t0 = time.time()
            logger.info(f"=== {label} ===")
            fn()
            logger.info(f"[TIMING] {label} finished in {time.time() - t0:.1f}s")
    except KeyboardInterrupt:
        logger.warning("[ABORTED] interrupted by user")
        sys.exit(130)

    total = time.time() - started
    logger.info(f"[TOTAL] pipeline finished in {total:.1f}s ({total / 60:.1f} min)")


if __name__ == "__main__":
    main()
