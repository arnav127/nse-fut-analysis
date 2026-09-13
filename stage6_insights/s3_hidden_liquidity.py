"""Concealed size: how much of the book is not shown, and how much of it trades.

Order-by-order data is the only way to see this. A disclosed-quantity order shows a slice and
replenishes it as the slice fills, so in a depth feed it looks like a series of small
independent orders arriving at the same price. The order file names the parent, and the book
replay tracks the concealed remainder, so both the resting concealed size and the executions
against it can be counted.

Four measures, in increasing order of how hard they are to fake with a depth feed.

  concealed depth   resting hidden quantity as a share of total resting quantity
  active icebergs   how many parents with a concealed remainder are live at once
  replenishment     refills per thousand shares matched - the rate at which concealed size
                    is being converted into executions
  hidden execution  the share of matched volume that came from concealed rather than
                    displayed size

The last is the one that matters for the settlement question. Someone accumulating or
distributing into a benchmark window has an obvious reason to conceal: the displayed order
would otherwise tell every other participant exactly what the settlement is being pushed
towards.
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

logger = setup_logger("Hidden", "stage6_insights.log")


def run_s3_hidden_liquidity() -> pd.DataFrame:
    snaps = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    orders = (Path(ENRICHED_DATA_DIR) / "cash_orders" / "date=*" / "sym=*" / "*.parquet").as_posix()
    out_csv = Path(RESULTS_DIR) / "s3_hidden_liquidity.csv"

    logger.info("[S3] concealed depth, replenishment and hidden execution")

    query = f"""
    WITH book AS (
        SELECT
            symbol, session, trade_date, is_expiry,
            AVG(CAST(resting_hidden AS DOUBLE)) AS mean_hidden_qty,
            AVG(CAST(total_bid_volume + total_ask_volume AS DOUBLE)) AS mean_visible_qty,
            AVG(CAST(active_icebergs AS DOUBLE)) AS mean_active_icebergs,
            AVG(CAST(live_orders AS DOUBLE)) AS mean_live_orders,
            AVG(CAST(touch_bid_iceberg_hidden + touch_ask_iceberg_hidden AS DOUBLE))
                AS mean_touch_hidden,
            SUM(CAST(interval_replenishments AS DOUBLE)) AS replenishments,
            SUM(CAST(interval_volume_matched AS DOUBLE)) AS matched_volume,
            SUM(CAST(interval_fills AS DOUBLE)) AS fills
        FROM read_parquet('{snaps}')
        GROUP BY symbol, session, trade_date, is_expiry
    ),
    submissions AS (
        -- Measured on entries only. A modify or cancel restates the remaining quantity of an
        -- order already counted, so including them would weight long-lived orders by how
        -- often they were amended.
        SELECT
            symbol, trade_date,
            COUNT(*) AS entries,
            SUM(CASE WHEN is_iceberg THEN 1 ELSE 0 END) AS concealed_entries,
            SUM(CAST(volume_original AS DOUBLE)) AS submitted_qty,
            SUM(CAST(hidden_volume AS DOUBLE)) AS concealed_qty,
            AVG(CASE WHEN is_iceberg
                     THEN CAST(volume_original AS DOUBLE) END) AS mean_concealed_parent_size,
            AVG(CASE WHEN NOT is_iceberg
                     THEN CAST(volume_original AS DOUBLE) END) AS mean_plain_size,
            SUM(CASE WHEN is_iceberg AND participant_type = 'Proprietary' THEN 1 ELSE 0 END)
                AS concealed_proprietary,
            SUM(CASE WHEN is_iceberg AND participant_type = 'Custodian' THEN 1 ELSE 0 END)
                AS concealed_custodian
        FROM read_parquet('{orders}')
        WHERE is_settlement_window AND activity_type = 1
        GROUP BY symbol, trade_date
    )
    SELECT
        b.symbol, b.session, b.trade_date, b.is_expiry,
        {sql_case(column="b.symbol")},
        b.mean_hidden_qty,
        b.mean_visible_qty,
        b.mean_hidden_qty / NULLIF(b.mean_hidden_qty + b.mean_visible_qty, 0)
            AS concealed_depth_share,
        b.mean_active_icebergs,
        b.mean_active_icebergs / NULLIF(b.mean_live_orders, 0) AS active_iceberg_share,
        b.mean_touch_hidden,
        b.replenishments,
        b.matched_volume,
        -- Refills per thousand shares matched. Normalising by volume is what makes this
        -- comparable across securities and sessions; the raw count just tracks turnover.
        b.replenishments * 1000.0 / NULLIF(b.matched_volume, 0) AS replenishment_rate,
        b.replenishments / NULLIF(b.fills, 0) AS replenishments_per_fill,
        s.entries,
        s.concealed_entries * 1.0 / NULLIF(s.entries, 0) AS concealed_entry_share,
        s.concealed_qty / NULLIF(s.submitted_qty, 0) AS concealed_volume_share,
        s.mean_concealed_parent_size,
        s.mean_plain_size,
        s.mean_concealed_parent_size / NULLIF(s.mean_plain_size, 0) AS concealed_size_multiple,
        s.concealed_proprietary * 1.0 / NULLIF(s.concealed_entries, 0)
            AS concealed_proprietary_share,
        s.concealed_custodian * 1.0 / NULLIF(s.concealed_entries, 0)
            AS concealed_custodian_share
    FROM book b
    LEFT JOIN submissions s ON b.symbol = s.symbol AND b.trade_date = s.trade_date
    ORDER BY b.symbol, b.trade_date
    """

    try:
        with duckdb.connect() as conn:
            result = conn.execute(query).df()
    except Exception as exc:
        logger.error(f"[S3] failed: {exc}")
        return pd.DataFrame()

    result.to_csv(out_csv, index=False)
    logger.info(f"[S3] {len(result)} symbol-sessions -> {out_csv}")
    return result


if __name__ == "__main__":
    frame = run_s3_hidden_liquidity()
    print(frame.groupby("is_expiry")[
        ["concealed_depth_share", "active_iceberg_share", "replenishment_rate",
         "concealed_entry_share", "concealed_volume_share", "concealed_size_multiple",
         "concealed_proprietary_share"]].mean().to_string())
