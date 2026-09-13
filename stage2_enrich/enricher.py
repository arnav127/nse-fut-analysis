"""Stage 2: derive the analysis columns onto the parsed tick data, one session at a time.

What this stage no longer does, because nsetick did it during the parse: convert jiffies to
timestamps, strip symbol padding, and decode 'Y'/'N' flags. What it still does is turn the
exchange's raw codes into the variables the hypotheses are stated in - participant class,
algo class, activity kind - and attach each row to a trading session and window.

Two changes of substance from the DuckDB enricher this replaces.

*It is incremental.* The old version read `parsed/<feed>/**/*.parquet` - every session at
once - and rewrote the entire enriched layer on each run, so adding one session meant
redoing twenty-four. Enrichment is row-local; nothing here needs another session's rows.

*Dates are unambiguous.* Every row carries both `session` (`27012022`, the NSE file's own
name, which the expiry calendar is written in) and `trade_date` (ISO, derived from the
timestamp). The old layer had only ISO `trade_date`, which meant any comparison against the
expiry list matched nothing - not an error, just an empty result.
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

from utils.duck import connect

from config.categories import CATEGORIES
from config.settings import (
    ALL_TARGET_DATES,
    EXPIRY_THURSDAYS_DDMMYYYY,
    SETTLEMENT_WINDOW_END,
    PARQUET_COMPRESSION,
    SETTLEMENT_WINDOW_START,
    TARGET_SYMBOLS,
)
from utils.logger import setup_logger
from utils.paths import enriched_dir, parsed_dir, session_to_iso
from utils.progress import Elapsed

logger = setup_logger("Enricher", "stage2_enrich.log")

# Exchange code books, from the layout specification's field documentation.
PARTICIPANT_CODES = {1: "Custodian", 2: "Proprietary", 3: "NCNP"}
ALGO_CODES = {0: "Algo", 1: "Non-Algo", 2: "Algo-SOR", 3: "Non-Algo-SOR"}
ACTIVITY_CODES = {1: "Entry", 3: "Cancel", 4: "Modify"}

# Prices arrive as integer paise with a `scale: 2` tag on the Arrow field. Converting to
# rupees here, once, keeps every downstream analysis in the unit its output is reported in.
PRICE_COLUMNS = {"limit_price", "trigger_price", "trade_price", "strike_price"}

# Feeds whose enriched layer is narrowed to the settlement window.
#
# Only orders. Ninety-four per cent of a session's order events fall outside the window and
# no analysis reads them: every order measure is a window measure, and the book replay works
# from the parsed layer, which keeps the whole session, so books are still built from the
# open. Carrying them anyway cost twelve of the thirteen gigabytes this layer occupied, which
# is what put a universe of any size out of reach.
#
# Trades keep the whole session. They are two per cent of the volume of orders, and the
# realised-variance and Amihud measures compare the window against the rest of the day, so
# the pre-window tape is genuinely read.
WINDOW_ONLY_CATEGORIES = {"cash_orders", "fao_orders"}


def _case(column: str, codes: dict, alias: str) -> str:
    arms = " ".join(f"WHEN {code} THEN '{label}'" for code, label in codes.items())
    return f"CASE {column} {arms} ELSE 'Unknown' END AS {alias}"


def _derived_columns(available: List[str], session: str) -> List[str]:
    """The columns this stage adds, given what the feed actually provides."""
    is_expiry = "TRUE" if session in EXPIRY_THURSDAYS_DDMMYYYY else "FALSE"
    out = [
        f"'{session}' AS session",
        f"'{session_to_iso(session)}' AS trade_date",
        "strftime(txn_time, '%H:%M:%S') AS trade_time",
        "strftime(txn_time, '%H:%M:00') AS time_bucket",
        # Compared as TIME rather than as text. The old string comparison happened to work
        # for zero-padded HH:MM:SS, but it silently depended on that formatting.
        f"(CAST(txn_time AS TIME) BETWEEN TIME '{SETTLEMENT_WINDOW_START}' "
        f"AND TIME '{SETTLEMENT_WINDOW_END}') AS is_settlement_window",
        f"{is_expiry} AS is_expiry",
        # Pre-open auction records share the file with continuous trading but are matched by
        # a call auction, not by the book. Flagging them lets an analysis exclude them
        # explicitly instead of relying on a time window to do it by accident.
        "(record_indicator = 'RM') AS is_regular_market",
    ]
    if "client_identity" in available:
        out.append(_case("client_identity", PARTICIPANT_CODES, "participant_type"))
    if "buy_client_identity" in available:
        out.append(_case("buy_client_identity", PARTICIPANT_CODES, "buy_participant_type"))
        out.append(_case("sell_client_identity", PARTICIPANT_CODES, "sell_participant_type"))
    if "algo_indicator" in available:
        out.append(_case("algo_indicator", ALGO_CODES, "algo_type"))
    if "buy_algo_indicator" in available:
        out.append(_case("buy_algo_indicator", ALGO_CODES, "buy_algo_type"))
        out.append(_case("sell_algo_indicator", ALGO_CODES, "sell_algo_type"))
    if "activity_type" in available:
        out.append(_case("activity_type", ACTIVITY_CODES, "activity_label"))
    if {"volume_disclosed", "volume_original"} <= set(available):
        # An order is an iceberg when it discloses a positive quantity smaller than its
        # total. Disclosed == 0 means no disclosed-quantity instruction at all, which is the
        # ordinary case and not an iceberg - the distinction the A6 analysis turns on.
        out.append(
            "(volume_disclosed > 0 AND volume_disclosed < volume_original) AS is_iceberg"
        )
        out.append(
            "CASE WHEN volume_disclosed > 0 AND volume_disclosed < volume_original "
            "THEN CAST(volume_original AS BIGINT) - CAST(volume_disclosed AS BIGINT) "
            "ELSE 0 END AS hidden_volume"
        )
    return out


def enrich_session(
    session: str,
    category_name: str,
    symbols: Optional[List[str]] = None,
    force: bool = False,
    memory_limit_mb: Optional[int] = None,
    threads: Optional[int] = None,
) -> Optional[Path]:
    """Enrich one feed for one session. Returns the output directory, or None if skipped."""
    src = parsed_dir(category_name, session)
    out_dir = enriched_dir(category_name, session)

    if not any(src.glob("symbol=*")):
        logger.info(f"[ABSENT] nothing parsed for {category_name} {session}")
        return None
    if any(out_dir.glob("sym=*")) and not force:
        logger.info(f"[SKIP] {category_name} {session} already enriched")
        return out_dir

    pattern = (src / "symbol=*" / "*.parquet").as_posix()
    elapsed = Elapsed()

    with connect(memory_limit_mb, threads) as conn:
        # `symbol` is not a column inside the files - nsetick partitions on it, so it lives
        # in the path. Hive partitioning is requested explicitly, here and in the query
        # below, rather than left to DuckDB's auto-detection; the old CLOB stage relied on
        # that detection and would have lost the column outright had it ever changed.
        available = [
            row[0] for row in
            conn.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{pattern}', hive_partitioning = true)"
            ).fetchall()
        ]
        # `date` comes from the path too, and would duplicate `session` under a name that
        # shadows a type.
        available = [c for c in available if c != "date"]
        base = [
            f"CAST({c} AS DOUBLE) / 100.0 AS {c}" if c in PRICE_COLUMNS else c
            for c in available
        ]
        clauses = []
        if symbols:
            quoted = ", ".join(f"'{s}'" for s in symbols)
            clauses.append(f"symbol IN ({quoted})")
        if category_name in WINDOW_ONLY_CATEGORIES:
            clauses.append(
                f"CAST(txn_time AS TIME) BETWEEN TIME '{SETTLEMENT_WINDOW_START}' "
                f"AND TIME '{SETTLEMENT_WINDOW_END}'")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        derived = _derived_columns(available, session)
        query = f"""
        SELECT
            {', '.join(base)},
            txn_time AS txn_datetime,
            symbol AS sym,
            {', '.join(derived)}
        FROM read_parquet('{pattern}', hive_partitioning = true)
        {where}
        """

        # Staged beside the destination so the move that publishes it is a rename on the
        # same volume, and so a failed run leaves the previous session's output intact.
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = out_dir.parent / f"_staging_{session}"
        shutil.rmtree(staging, ignore_errors=True)
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

    logger.info(f"[DONE] {category_name} {session}: {rows:,} rows enriched in {elapsed}")
    return out_dir


def run_enrich(
    single_date: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    force: bool = False,
    memory_limit_mb: Optional[int] = None,
    threads: Optional[int] = None,
) -> None:
    """Enrich every feed for the configured sessions.

    Narrowed to `TARGET_SYMBOLS` by default. Stage 1 deliberately keeps the whole EQ
    cross-section so that widening the study never means re-reading the compressed files,
    but carrying every symbol through enrichment and into the analyses would multiply the
    layer by two orders of magnitude to no purpose.
    """
    sessions = [single_date] if single_date else ALL_TARGET_DATES
    if symbols is None:
        symbols = TARGET_SYMBOLS

    logger.info(f"=== STAGE 2: ENRICH ({len(sessions)} sessions) ===")
    started = time.time()
    for session in sessions:
        for name in CATEGORIES:
            try:
                enrich_session(session, name, symbols=symbols, force=force,
                               memory_limit_mb=memory_limit_mb, threads=threads)
            except Exception as exc:
                logger.error(f"[FAILED] enrich {name} {session}: {exc}")
    logger.info(f"[COMPLETE] stage 2 finished in {time.time() - started:.1f}s")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Stage 2: enrich parsed tick data")
    ap.add_argument("--date", help="single session in DDMMYYYY form")
    ap.add_argument("--all-symbols", action="store_true", help="do not narrow to TARGET_SYMBOLS")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    run_enrich(single_date=args.date, symbols=[] if args.all_symbols else None, force=args.force)
