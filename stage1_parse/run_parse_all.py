"""Stage 1 orchestrator: parse every target session."""

from __future__ import annotations

import time
from typing import List, Optional

from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS
from stage1_parse.tick_parser import parse_session
from utils.logger import setup_logger

logger = setup_logger("Stage1", "stage1_parse.log")


def run_parse(
    single_date: Optional[str] = None,
    universe_only: bool = False,
    force: bool = False,
) -> None:
    """Parse raw NSE files for the configured sessions.

    Parses the whole EQ / FUTSTK cross-section by default rather than only the ten target
    symbols. The extra cost is small - nsetick's filter is a bucketed set lookup, and the
    universe is what determines output size, not decode time - and it means adding a symbol
    to the study does not require re-reading every compressed session from the start.
    Pass `universe_only` to restrict the parse when disk is the binding constraint.
    """
    sessions: List[str] = [single_date] if single_date else ALL_TARGET_DATES
    symbols = TARGET_SYMBOLS if universe_only else None

    logger.info(f"=== STAGE 1: PARSE ({len(sessions)} sessions) ===")
    started = time.time()
    for index, session in enumerate(sessions, 1):
        logger.info(f"--- [{index:02d}/{len(sessions):02d}] session {session} ---")
        t0 = time.time()
        parse_session(session, symbols=symbols, force=force)
        logger.info(f"[TIMING] session {session} parsed in {time.time() - t0:.1f}s")

    logger.info(f"[COMPLETE] stage 1 finished in {time.time() - started:.1f}s")


if __name__ == "__main__":
    run_parse()
