"""Stage 4 orchestrator.

No multiprocessing pool here any more. The old runner fanned out one Python process per
(symbol, session) pair because the book was a Python loop and that was the only way to use
more than one core. nsetick already fans out across symbols inside a single call, and
running several of those concurrently would contend for the same cores and the same disk
while multiplying peak memory by the number of workers.
"""

from __future__ import annotations

import time
from typing import List, Optional

from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS
from stage4_clob.clob_builder import build_clob_for_session
from utils.logger import setup_logger

logger = setup_logger("Stage4", "stage4_clob.log")


def run_clob(
    single_date: Optional[str] = None,
    single_symbol: Optional[str] = None,
    force: bool = False,
) -> None:
    sessions: List[str] = [single_date] if single_date else ALL_TARGET_DATES
    symbols: List[str] = [single_symbol] if single_symbol else TARGET_SYMBOLS

    logger.info(f"=== STAGE 4: CLOB RECONSTRUCTION ({len(sessions)} sessions x {len(symbols)} symbols) ===")
    started = time.time()
    for session in sessions:
        try:
            build_clob_for_session(session, symbols=symbols, force=force)
        except Exception as exc:
            logger.error(f"[FAILED] CLOB {session}: {exc}")
    logger.info(f"[COMPLETE] stage 4 finished in {time.time() - started:.1f}s")


if __name__ == "__main__":
    run_clob()
