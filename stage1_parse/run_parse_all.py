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
    all_eq: bool = False,
    force: bool = False,
) -> None:
    """Parse raw NSE files for the configured sessions.

    Restricted to `TARGET_SYMBOLS` by default. Decoding is the same cost either way -
    nsetick reads every record regardless and the filter is a bucketed set lookup - but the
    output is not: a session holds roughly 1,900 EQ symbols and the study uses ten, so
    keeping them all writes about two orders of magnitude more Parquet than anything
    downstream reads. Pass `all_eq` when the extra symbols will actually be used; widening
    the study later then costs one reparse rather than being free.
    """
    sessions: List[str] = [single_date] if single_date else ALL_TARGET_DATES
    symbols = None if all_eq else TARGET_SYMBOLS

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
