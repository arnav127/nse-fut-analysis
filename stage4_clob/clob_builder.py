"""Stage 4: limit order book reconstruction and periodic L2 snapshots, via nsetick.

This replaces a Python `SortedDict` book (with an optional C++ PyBind11 twin) driven from a
pandas row loop. Three things were wrong with it, in descending order of how much they
distort the result:

*Disclosed quantity was ignored.* The book rested `volume_original` at the order's price.
For a disclosed-quantity order only `volume_disclosed` is visible; the remainder is hidden
and replenishes - losing queue priority each time - as the visible slice fills. Resting the
full quantity overstates visible depth at exactly the prices where large orders sit, which
is the measurement stage 5 exists to make.

*Modify was treated as cancel-and-replace at the same quantity.* An NSE modify that reduces
quantity or leaves price untouched keeps its place in the queue; only a price change or a
quantity increase forfeits it. Re-adding unconditionally moves every modified order to the
back.

*Partial fills against a modified order desynchronised.* `remove_traded_qty` decremented the
level by the traded quantity whether or not the order's recorded state still matched the
book, so a level could be decremented twice or not at all, and the error accumulated across
the session with nothing to detect it.

nsetick replays the same events in Rust with disclosed-quantity replenishment and the
queue-priority rules, fans out across symbols, and reports hidden as well as visible size at
every level. This module runs it and flattens its output into the column names the stage-5
analyses read.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import nsetick

from utils.duck import connect

from config.settings import (
    CLOB_BOOKS_DIR,
    CLOB_DATA_DIR,
    CLOB_DEPTH_LEVELS,
    CLOB_DEPTH_SUM_LEVELS,
    CLOB_REPORTED_LEVELS,
    CLOB_SNAPSHOT_INTERVAL_SECONDS,
    EXPIRY_THURSDAYS_DDMMYYYY,
    NSETICK_THREADS,
    PARQUET_COMPRESSION,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
    TARGET_SYMBOLS,
)
from utils.logger import setup_logger
from utils.paths import clob_dir, parsed_dir, promote_hive_partitions, session_to_iso
from utils.progress import track_symbols

logger = setup_logger("CLOB", "stage4_clob.log")

PAISE = 100.0


def books_dir(session: str) -> Path:
    return CLOB_BOOKS_DIR / f"date={session}"


def build_books(session: str, symbols: Optional[List[str]] = None, force: bool = False,
                threads: Optional[int] = None) -> Optional[Path]:
    """Replay the session's orders into per-symbol books and write L2 snapshots."""
    src = parsed_dir("cash_orders", session)
    out = books_dir(session)

    if not any(src.glob("symbol=*")):
        logger.warning(f"[ABSENT] no parsed cash orders for {session}; run stage 1 first")
        return None
    if any(out.glob("symbol=*")) and not force:
        logger.info(f"[SKIP] books for {session} already built")
        return out

    symbols = symbols or TARGET_SYMBOLS
    shutil.rmtree(out, ignore_errors=True)
    staging = out / "_staging"
    staging.mkdir(parents=True)

    logger.info(f"[BOOKS] {session}: replaying {len(symbols)} symbols at "
                f"{CLOB_SNAPSHOT_INTERVAL_SECONDS}s, {CLOB_DEPTH_LEVELS} levels")
    started = time.time()
    # Reads the parsed directory rather than the raw .DAT.gz: the events are already
    # decoded and split by symbol, so the replay parallelises per symbol instead of
    # re-reading one compressed stream.
    try:
        with track_symbols(staging, total=len(symbols), desc=f"books {session}"):
            report = nsetick.build_books(
                input=src.as_posix(),
                out=staging.as_posix(),
                date=session_to_iso(session),
                interval_secs=CLOB_SNAPSHOT_INTERVAL_SECONDS,
                levels=CLOB_DEPTH_LEVELS,
                symbols=symbols,
                threads=threads or NSETICK_THREADS,
                compression=PARQUET_COMPRESSION,
            )
        partitions = promote_hive_partitions(staging, out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    logger.info(f"[BOOKS] {session}: {report.get('snapshots', 0):,} snapshots across "
                f"{partitions} symbols in {time.time() - started:.1f}s")
    return out


def _snapshot_projection(levels: int) -> str:
    """nsetick's book columns, renamed and rescaled into the stage-5 contract.

    Depth totals are summed over the reported levels rather than taken from nsetick's
    whole-book `total_bid_visible`. The stage-5 erosion measure is about the top of the
    book, and a whole-book total would also move whenever a far-away level appeared.
    """
    # Depth totals stay on the first ten levels whatever the snapshot carries: that is what
    # "top of book depth" has meant throughout, and widening it silently would change the
    # meaning of every depth result rather than adding to it.
    summed = min(CLOB_DEPTH_SUM_LEVELS, levels)
    bid_qty = [f"COALESCE(bid_qty_{i}, 0)" for i in range(1, summed + 1)]
    ask_qty = [f"COALESCE(ask_qty_{i}, 0)" for i in range(1, summed + 1)]
    depth_cols = [f"COALESCE(bid_qty_{i}, 0) AS bid_depth_{i}" for i in range(1, levels + 1)]
    depth_cols += [f"COALESCE(ask_qty_{i}, 0) AS ask_depth_{i}" for i in range(1, levels + 1)]
    # Hidden size has no counterpart in the old schema; it is what the previous book could
    # not see at all, so it is carried through alongside the visible depth.
    depth_cols += [f"COALESCE(bid_hidden_{i}, 0) AS bid_hidden_{i}" for i in range(1, levels + 1)]
    depth_cols += [f"COALESCE(ask_hidden_{i}, 0) AS ask_hidden_{i}" for i in range(1, levels + 1)]
    # Level prices, in rupees. Quantity alone describes how much is resting but not where,
    # and every cost-of-execution measure - what it takes to move the mid, the slope of the
    # book, the notional behind a walk of N levels - needs the distance from the touch.
    depth_cols += [f"bid_px_{i} / {PAISE} AS bid_px_{i}" for i in range(1, levels + 1)]
    depth_cols += [f"ask_px_{i} / {PAISE} AS ask_px_{i}" for i in range(1, levels + 1)]

    bid_sum = " + ".join(bid_qty)
    ask_sum = " + ".join(ask_qty)
    return f"""
        symbol,
        snapshot_time,
        strftime(snapshot_time, '%H:%M:%S') AS snapshot_hms,
        best_bid / {PAISE} AS best_bid,
        best_ask / {PAISE} AS best_ask,
        mid_price / {PAISE} AS midpoint,
        spread / {PAISE} AS spread,
        CASE WHEN mid_price > 0 THEN spread * 10000.0 / mid_price END AS spread_bps,
        ({bid_sum}) AS total_bid_volume,
        ({ask_sum}) AS total_ask_volume,
        CASE WHEN ({bid_sum}) + ({ask_sum}) > 0
             THEN (({bid_sum}) - ({ask_sum})) * 1.0 / (({bid_sum}) + ({ask_sum}))
             ELSE 0.0 END AS book_imbalance,
        resting_hidden,
        active_icebergs,
        live_orders,
        touch_bid_iceberg_hidden,
        touch_ask_iceberg_hidden,
        interval_entries,
        interval_cancels,
        interval_fills,
        interval_volume_matched,
        interval_replenishments,
        is_crossed,
        {', '.join(depth_cols)}
    """


def flatten_snapshots(session: str, force: bool = False,
                      memory_limit_mb: Optional[int] = None,
                      threads: Optional[int] = None) -> Optional[Path]:
    """Project the raw book output into the snapshot table stage 5 reads.

    Restricted to the settlement window. The book itself is replayed from the session open -
    it has to be, or depth at 15:00 would be whatever had accumulated since 15:00 - but only
    the window is retained, which is the same scope the previous stage wrote.
    """
    src = books_dir(session)
    out_dir = clob_dir(session)

    if not any(src.glob("symbol=*")):
        logger.warning(f"[ABSENT] no books for {session}")
        return None
    if any(out_dir.glob("sym=*")) and not force:
        logger.info(f"[SKIP] snapshots for {session} already flattened")
        return out_dir

    pattern = (src / "symbol=*" / "*.parquet").as_posix()
    is_expiry = "TRUE" if session in EXPIRY_THURSDAYS_DDMMYYYY else "FALSE"
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = out_dir.parent / f"_staging_{session}"
    shutil.rmtree(staging, ignore_errors=True)

    query = f"""
    SELECT
        {_snapshot_projection(CLOB_REPORTED_LEVELS)},
        symbol AS sym,
        '{session}' AS session,
        '{session_to_iso(session)}' AS trade_date,
        {is_expiry} AS is_expiry,
        CAST(date_diff('second', CAST(snapshot_time AS DATE) + TIME '{SETTLEMENT_WINDOW_START}',
                       snapshot_time) AS BIGINT) AS seconds_from_1500
    FROM read_parquet('{pattern}', hive_partitioning = true)
    WHERE CAST(snapshot_time AS TIME)
          BETWEEN TIME '{SETTLEMENT_WINDOW_START}' AND TIME '{SETTLEMENT_WINDOW_END}'
    """

    with connect(memory_limit_mb, threads) as conn:
        conn.execute(
            f"COPY ({query}) TO '{staging.as_posix()}' "
            f"(FORMAT PARQUET, COMPRESSION '{PARQUET_COMPRESSION.upper()}', PARTITION_BY (sym), OVERWRITE_OR_IGNORE 1)"
        )
        rows = conn.execute(
            f"SELECT count(*) FROM read_parquet('{(staging / '**' / '*.parquet').as_posix()}')"
        ).fetchone()[0]

    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(out_dir))
    logger.info(f"[SNAPSHOTS] {session}: {rows:,} settlement-window snapshots -> {out_dir}")
    return out_dir


def build_clob_for_session(session: str, symbols: Optional[List[str]] = None,
                           force: bool = False, memory_limit_mb: Optional[int] = None,
                           threads: Optional[int] = None) -> None:
    if build_books(session, symbols=symbols, force=force, threads=threads) is not None:
        flatten_snapshots(session, force=force, memory_limit_mb=memory_limit_mb,
                          threads=threads)
