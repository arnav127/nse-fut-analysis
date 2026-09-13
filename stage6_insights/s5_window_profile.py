"""How the window evolves minute by minute, rather than what it averages to.

Every measure elsewhere in the study is a window average, and an average cannot distinguish
a window that is uniformly different from one whose last three minutes are different. Those
two are not the same claim: influence on an average price is cheapest at the end, when there
is no time left for the rest of the window to dilute it, so a settlement effect should show
as a shape rather than as a level.

This produces the series behind the report's figures: each measure by minute from the
window's open, split by whether the session is an expiry and by which group the security
belongs to. The placebo group appears on the same axes, which is what turns a plot of two
lines into a test - if the expiry and control lines separate for the derivative groups and
lie on top of each other for the placebo, the separation is a settlement effect rather than
a last-Thursday-of-the-month effect.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402

from config.settings import CLOB_DATA_DIR, ENRICHED_DATA_DIR, RESULTS_DIR  # noqa: E402
from config.universe import sql_case  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Profile", "stage6_insights.log")


def run_s5_window_profile() -> pd.DataFrame:
    snaps = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    orders = (Path(ENRICHED_DATA_DIR) / "cash_orders" / "date=*" / "sym=*" / "*.parquet").as_posix()
    out_csv = Path(RESULTS_DIR) / "s5_window_profile.csv"

    logger.info("[S5] building the minute-by-minute window profile")

    query = f"""
    WITH book AS (
        SELECT
            symbol, trade_date, is_expiry,
            seconds_from_1500 // 60 AS minute,
            spread_bps, book_imbalance,
            CAST(total_bid_volume + total_ask_volume AS DOUBLE) AS depth,
            CAST(resting_hidden AS DOUBLE) AS hidden,
            CAST(interval_volume_matched AS DOUBLE) AS matched,
            CAST(interval_cancels AS DOUBLE) AS cancels,
            CAST(interval_entries AS DOUBLE) AS entries,
            CAST(interval_replenishments AS DOUBLE) AS replenishments
        FROM read_parquet('{snaps}')
    ),
    book_minute AS (
        SELECT
            symbol, trade_date, is_expiry, minute,
            AVG(spread_bps) AS spread_bps,
            AVG(depth) AS depth,
            AVG(ABS(book_imbalance)) AS abs_imbalance,
            AVG(hidden / NULLIF(hidden + depth, 0)) AS concealed_share,
            SUM(matched) AS matched_volume,
            SUM(cancels) AS cancels,
            SUM(entries) AS entries,
            SUM(replenishments) AS replenishments
        FROM book
        GROUP BY symbol, trade_date, is_expiry, minute
    ),
    order_minute AS (
        SELECT
            symbol, trade_date,
            date_diff('minute', CAST(txn_datetime AS DATE) + TIME '15:00:00',
                      txn_datetime) AS minute,
            COUNT(*) FILTER (WHERE activity_type = 1) AS submissions,
            AVG(CASE WHEN activity_type = 1 AND ioc_flag THEN 1.0
                     WHEN activity_type = 1 THEN 0.0 END) AS ioc_share,
            AVG(CASE WHEN activity_type = 1 AND is_iceberg THEN 1.0
                     WHEN activity_type = 1 THEN 0.0 END) AS concealed_entry_share,
            SUM(CASE WHEN activity_type = 1 THEN CAST(volume_original AS DOUBLE) END)
                AS submitted_qty
        FROM read_parquet('{orders}')
        WHERE is_settlement_window AND is_regular_market
        GROUP BY symbol, trade_date, minute
    )
    SELECT
        b.symbol, b.trade_date, b.is_expiry, b.minute,
        {sql_case(column="b.symbol")},
        b.spread_bps, b.depth, b.abs_imbalance, b.concealed_share,
        b.matched_volume, b.cancels, b.entries, b.replenishments,
        b.cancels / NULLIF(b.entries, 0) AS cancel_to_entry,
        b.replenishments * 1000.0 / NULLIF(b.matched_volume, 0) AS replenishment_rate,
        o.submissions, o.ioc_share, o.concealed_entry_share, o.submitted_qty
    FROM book_minute b
    LEFT JOIN order_minute o
      ON b.symbol = o.symbol AND b.trade_date = o.trade_date AND b.minute = o.minute
    WHERE b.minute BETWEEN 0 AND 29
    ORDER BY b.symbol, b.trade_date, b.minute
    """

    try:
        with duckdb.connect() as conn:
            detail = conn.execute(query).df()
    except Exception as exc:
        logger.error(f"[S5] failed: {exc}")
        return pd.DataFrame()

    detail.to_csv(RESULTS_DIR / "s5_window_profile_detail.csv", index=False)

    # Each security-session contributes one observation per minute, so the group average is
    # a mean over securities and months rather than over volume - a single very active name
    # would otherwise be the entire line.
    measures = ["spread_bps", "depth", "abs_imbalance", "concealed_share", "matched_volume",
                "cancel_to_entry", "replenishment_rate", "ioc_share",
                "concealed_entry_share", "submissions"]
    profile = (detail.groupby(["security_group", "is_expiry", "minute"], as_index=False)
               [measures].mean())
    # Volume is reported as a share of the session's own window total, so securities of very
    # different sizes can be averaged onto one curve.
    totals = detail.groupby(["symbol", "trade_date"], as_index=False).matched_volume.sum()
    totals = totals.rename(columns={"matched_volume": "session_volume"})
    shares = detail.merge(totals, on=["symbol", "trade_date"])
    shares["volume_share"] = shares.matched_volume / shares.session_volume.replace(0, pd.NA)
    volume_profile = (shares.groupby(["security_group", "is_expiry", "minute"], as_index=False)
                      .volume_share.mean())
    profile = profile.merge(volume_profile, on=["security_group", "is_expiry", "minute"])

    profile.to_csv(out_csv, index=False)
    logger.info(f"[S5] {len(profile)} group-minute rows -> {out_csv}")
    return profile


if __name__ == "__main__":
    frame = run_s5_window_profile()
    if not frame.empty:
        last = frame[frame.minute >= 27]
        print(last.groupby(["security_group", "is_expiry"])[
            ["spread_bps", "volume_share", "concealed_share", "cancel_to_entry"]].mean().to_string())
