"""One row per security and session, for every trading session of 2022.

The book-based analyses need the order file and a replay of the book, which is why they run
on twenty-four sessions. The settlement price itself needs only the trade tape, and the
tape for a full year of sessions is cheap to read when it is reduced as it is parsed. This
module does that: each session's trade file is decoded for the study universe only, reduced
to the handful of prices, volumes and signed flows the settlement tests need, and the decoded
trades are discarded. What is kept is a few kilobytes per session.

Per security and session:

    open30_vwap        VWAP of the first thirty minutes of continuous trading
    pre10_vwap         VWAP of the ten minutes before the settlement window
    pre_last           last trade before the window
    settle_vwap        VWAP of the settlement window, which is the exchange's closing price
    w1_vwap..w6_vwap   VWAP of each five-minute part of the window
    close_last         last trade of the session
    window_signed      net aggressor-signed volume in the window, in shares
    window_signed_p*   the same, split by the aggressor's participant category
    window_volume_p*   window volume with that participant category on either side

The aggressor is the side whose order arrived later. Order numbers are assigned in arrival
order, so the side with the larger order number is the one that crossed the spread; on the
sessions for which both are available this agrees with entry times without exception.

Sessions already parsed for the book analyses are read from the parsed layer rather than
decoded a second time.
"""

from __future__ import annotations

import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from config.categories import CATEGORIES  # noqa: E402
from config.settings import (  # noqa: E402
    DATA_ROOT,
    PARQUET_COMPRESSION,
    RESULTS_DIR,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
    TARGET_SYMBOLS,
)
from stage9_tape.calendar import trading_sessions  # noqa: E402
from utils.duck import connect  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.paths import has_partitions, parsed_dir, raw_files  # noqa: E402

logger = setup_logger("Tape", "stage9_tape.log")

TAPE_DIR = Path(RESULTS_DIR) / "tape"
SCRATCH_DIR = Path(DATA_ROOT) / "tmp" / "tape"

# Participant categories as the trade file codes them.
PARTICIPANTS = {1: "custodian", 2: "proprietary", 3: "ncnp"}

OPEN_WINDOW_END = "09:45:00"
PRE_WINDOW_START = "14:50:00"
LAST_FIVE_START = "15:25:00"


def tape_path(session: str) -> Path:
    return TAPE_DIR / f"session={session}.parquet"


# Columns a current reduction carries; an older file without them is redone.
REQUIRED_COLUMNS = ("w1_bi", "first1_vwap")


def _current(path: Path) -> bool:
    if not path.exists():
        return False
    import pyarrow.parquet as pq

    names = set(pq.read_schema(path).names)
    return all(c in names for c in REQUIRED_COLUMNS)


def _reduction(pattern: str, session: str, symbols: List[str]) -> str:
    quoted = ", ".join(f"'{s}'" for s in symbols)
    start, end = SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
    window = f"tt >= TIME '{start}' AND tt <= TIME '{end}'"
    per_part = []
    for code, name in PARTICIPANTS.items():
        per_part.append(
            f"SUM(sgn * q) FILTER (WHERE {window} AND aggressor = {code}) "
            f"AS window_signed_{name}")
        per_part.append(
            f"SUM(q) FILTER (WHERE {window} AND (buy_client_identity = {code} "
            f"OR sell_client_identity = {code})) AS window_volume_{name}")
    sub_windows = []
    for k in range(6):
        lo = f"TIME '{start}' + INTERVAL {5 * k} MINUTE"
        hi = f"TIME '{start}' + INTERVAL {5 * (k + 1)} MINUTE"
        upper = "<=" if k == 5 else "<"
        sub_windows.append(
            f"SUM(px * q) FILTER (WHERE tt >= {lo} AND tt {upper} {hi}) / "
            f"NULLIF(SUM(q) FILTER (WHERE tt >= {lo} AND tt {upper} {hi}), 0) AS w{k + 1}_vwap")
        # Buyer- and seller-initiated volume in each block, for the order imbalance
        # (BI - SI) / (BI + SI) of each five minutes of the window.
        sub_windows.append(
            f"SUM(q) FILTER (WHERE sgn > 0 AND tt >= {lo} AND tt {upper} {hi}) AS w{k + 1}_bi")
        sub_windows.append(
            f"SUM(q) FILTER (WHERE sgn < 0 AND tt >= {lo} AND tt {upper} {hi}) AS w{k + 1}_si")
    # The price at the two ends of the window: the VWAP of its first and of its last minute.
    first_minute = f"tt >= TIME '{start}' AND tt < TIME '{start}' + INTERVAL 1 MINUTE"
    last_minute = f"tt >= TIME '{end}' - INTERVAL 1 MINUTE AND tt <= TIME '{end}'"
    for name, cond in (("first1_vwap", first_minute), ("last1_vwap", last_minute)):
        sub_windows.append(f"SUM(px * q) FILTER (WHERE {cond}) / "
                           f"NULLIF(SUM(q) FILTER (WHERE {cond}), 0) AS {name}")
    return f"""
    WITH t AS (
        SELECT symbol, txn_time,
               CAST(txn_time AS TIME) AS tt,
               CAST(trade_price AS DOUBLE) / 100.0 AS px,
               CAST(trade_quantity AS DOUBLE) AS q,
               CASE WHEN buy_order_number > sell_order_number THEN 1.0 ELSE -1.0 END AS sgn,
               CASE WHEN buy_order_number > sell_order_number THEN buy_client_identity
                    ELSE sell_client_identity END AS aggressor,
               buy_client_identity, sell_client_identity
        FROM read_parquet('{pattern}', hive_partitioning = true)
        WHERE record_indicator = 'RM' AND trade_quantity > 0 AND trade_price > 0
          AND symbol IN ({quoted})
    )
    SELECT
        '{session}' AS session,
        symbol,
        COUNT(*) AS n_trades,
        SUM(q) AS volume,
        SUM(px * q) AS turnover,
        arg_min(px, txn_time) AS open_price,
        SUM(px * q) FILTER (WHERE tt < TIME '{OPEN_WINDOW_END}')
            / NULLIF(SUM(q) FILTER (WHERE tt < TIME '{OPEN_WINDOW_END}'), 0) AS open30_vwap,
        SUM(px * q) FILTER (WHERE tt >= TIME '{PRE_WINDOW_START}' AND tt < TIME '{start}')
            / NULLIF(SUM(q) FILTER (WHERE tt >= TIME '{PRE_WINDOW_START}'
                                     AND tt < TIME '{start}'), 0) AS pre10_vwap,
        arg_max(px, txn_time) FILTER (WHERE tt < TIME '{start}') AS pre_last,
        SUM(px * q) FILTER (WHERE {window}) / NULLIF(SUM(q) FILTER (WHERE {window}), 0)
            AS settle_vwap,
        SUM(q) FILTER (WHERE {window}) AS window_volume,
        COUNT(*) FILTER (WHERE {window}) AS window_trades,
        {', '.join(sub_windows)},
        SUM(px * q) FILTER (WHERE tt >= TIME '{LAST_FIVE_START}' AND tt <= TIME '{end}')
            / NULLIF(SUM(q) FILTER (WHERE tt >= TIME '{LAST_FIVE_START}'
                                     AND tt <= TIME '{end}'), 0) AS last5_vwap,
        arg_max(px, txn_time) AS close_last,
        SUM(sgn * q) FILTER (WHERE {window}) AS window_signed,
        SUM(sgn * q) FILTER (WHERE tt >= TIME '14:30:00' AND tt < TIME '{start}')
            AS pre30_signed,
        SUM(q) FILTER (WHERE tt >= TIME '14:30:00' AND tt < TIME '{start}') AS pre30_volume,
        {', '.join(per_part)}
    FROM t
    GROUP BY symbol
    ORDER BY symbol
    """


def reduce_session(session: str, symbols: Optional[List[str]] = None, force: bool = False,
                   threads: Optional[int] = None,
                   memory_limit_mb: Optional[int] = None) -> Optional[Path]:
    """Reduce one session's trade tape to one row per security. Resumable."""
    import nsetick

    out = tape_path(session)
    if _current(out) and not force:
        return out
    symbols = symbols or TARGET_SYMBOLS
    started = time.time()

    source = parsed_dir("cash_trades", session)
    scratch = None
    if has_partitions(source):
        pattern = (source / "symbol=*" / "*.parquet").as_posix()
        origin = "parsed"
    else:
        files = raw_files(CATEGORIES["cash_trades"].file_prefix, session)
        if len(files) != 1:
            logger.error(f"[TAPE] {session}: expected one cash trade file, found {len(files)}")
            return None
        scratch = SCRATCH_DIR / session
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        quoted = ", ".join(f"'{s}'" for s in symbols)
        nsetick.parse(
            input=files[0], out=scratch.as_posix(), layout="cm_trades",
            where=f"{CATEGORIES['cash_trades'].where} and symbol in ({quoted})",
            partition_by="symbol", compression=PARQUET_COMPRESSION,
            threads=threads, memory_limit_mb=memory_limit_mb,
            note=f"ProjectCourse tape {session}")
        pattern = (scratch / "**" / "symbol=*" / "*.parquet").as_posix()
        origin = "raw"

    try:
        with connect(memory_limit_mb, threads) as conn:
            frame = conn.execute(_reduction(pattern, session, symbols)).df()
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)

    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    staging = out.with_suffix(".partial")
    frame.to_parquet(staging, index=False)
    staging.replace(out)
    logger.info(f"[TAPE] {session}: {len(frame)} securities from {origin} in "
                f"{time.time() - started:.1f}s")
    return out


def _worker(args) -> tuple:
    session, force, threads, memory = args
    try:
        reduce_session(session, force=force, threads=threads, memory_limit_mb=memory)
        return session, None
    except Exception as exc:  # recorded, so one bad file does not stop the year
        return session, f"{type(exc).__name__}: {exc}"


def run_tape(jobs: int = 1, force: bool = False, sessions: Optional[List[str]] = None,
             threads: Optional[int] = None, memory_limit_mb: Optional[int] = None) -> pd.DataFrame:
    """Reduce every 2022 session, `jobs` at a time, and return the stacked panel."""
    sessions = sessions or trading_sessions()
    todo = [s for s in sessions if force or not _current(tape_path(s))]
    logger.info(f"[TAPE] {len(sessions)} sessions, {len(todo)} to reduce, {jobs} at a time")
    failures = []
    if todo:
        work = [(s, force, threads, memory_limit_mb) for s in todo]
        if jobs <= 1:
            results = map(_worker, work)
        else:
            pool = ProcessPoolExecutor(max_workers=jobs)
            results = (f.result() for f in as_completed([pool.submit(_worker, w) for w in work]))
        for done, (session, error) in enumerate(results, 1):
            if error:
                failures.append(session)
                logger.error(f"[TAPE] {session} failed: {error}")
            elif done % 10 == 0:
                logger.info(f"[TAPE] {done}/{len(todo)} reduced")
    if failures:
        logger.warning(f"[TAPE] {len(failures)} sessions failed: {', '.join(failures)}")
    return load_tape()


def load_tape() -> pd.DataFrame:
    files = sorted(TAPE_DIR.glob("session=*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


if __name__ == "__main__":
    import argparse

    from utils.resources import worker_budget

    ap = argparse.ArgumentParser(description="Reduce the 2022 trade tape to a daily panel")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--session", action="append")
    args = ap.parse_args()
    memory, threads = worker_budget(args.jobs)
    panel = run_tape(jobs=args.jobs, force=args.force, sessions=args.session,
                     threads=threads, memory_limit_mb=memory)
    print(f"{len(panel):,} security-sessions across {panel.session.nunique()} sessions")
