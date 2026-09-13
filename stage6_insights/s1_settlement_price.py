"""The settlement price itself: what it is, and how far it sits from everything else.

The study is about a settlement VWAP, and the original pipeline never computed one. Every
measure was a property of the window - spreads, depth, cancellations - and none of them was
the number the window exists to produce. This module computes it and places it against three
benchmarks.

  drift        settlement VWAP against the mid at the window's open. If the window is being
               pushed, this is where it shows: the average price over the window ends up
               away from where the market stood when the window began.
  reversal     settlement VWAP against the closing price. A push that is abandoned once the
               settlement is struck leaves the close somewhere else. This is the sharpest
               available test that does not need the next session's data.
  terminal gap the final minute's VWAP against the whole window's. Settlement influence is
               cheapest at the end, when there is no time left for the average to recover.

Signs are kept but the tests are on absolute values. A participant long the future wants the
settlement high and one short wants it low, so across a cross-section of securities and
months the signed drift should average to roughly nothing whether or not anybody is pushing.
The dispersion is the quantity that carries the information, which is why the paired tests
use magnitudes and the signed series is retained only for the figures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402

from config.settings import (  # noqa: E402
    CLOB_DATA_DIR,
    ENRICHED_DATA_DIR,
    RESULTS_DIR,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
)
from config.universe import sql_case  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Settlement", "stage6_insights.log")

# How close a trade must be to the running VWAP to count as tracking it. One basis point is
# roughly a single tick on a mid-priced Indian equity, so this is "at the benchmark" rather
# than "near" it.
VWAP_TRACKING_TOLERANCE_BPS = 1.0


def run_s1_settlement_price() -> pd.DataFrame:
    trades = (Path(ENRICHED_DATA_DIR) / "cash_trades" / "date=*" / "sym=*" / "*.parquet").as_posix()
    snaps = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    out_csv = Path(RESULTS_DIR) / "s1_settlement_price.csv"

    logger.info("[S1] computing the settlement VWAP and its benchmarks")

    query = f"""
    WITH window_trades AS (
        SELECT
            symbol, session, trade_date, is_expiry, txn_datetime,
            trade_price, CAST(trade_quantity AS DOUBLE) AS qty,
            time_bucket
        FROM read_parquet('{trades}')
        WHERE is_settlement_window AND is_regular_market AND trade_quantity > 0
    ),
    running AS (
        SELECT
            *,
            -- The settlement VWAP as it stands at each trade. Computed over the rows
            -- preceding and including this one, which is the number a participant watching
            -- the benchmark in real time would see.
            SUM(trade_price * qty) OVER w / NULLIF(SUM(qty) OVER w, 0) AS vwap_so_far
        FROM window_trades
        WINDOW w AS (PARTITION BY symbol, trade_date ORDER BY txn_datetime
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ),
    per_session AS (
        SELECT
            symbol, session, trade_date, any_value(is_expiry) AS is_expiry,
            SUM(trade_price * qty) / SUM(qty) AS settle_vwap,
            SUM(qty) AS window_volume,
            COUNT(*) AS window_trades,
            LAST(trade_price ORDER BY txn_datetime) AS close_price,
            FIRST(trade_price ORDER BY txn_datetime) AS first_price,
            -- Share of volume transacted within a basis point of the benchmark as it then
            -- stood. High values indicate execution benchmarked to the VWAP rather than
            -- opportunistic trading.
            SUM(CASE WHEN vwap_so_far > 0
                     AND ABS(trade_price - vwap_so_far) / vwap_so_far * 10000.0
                         <= {VWAP_TRACKING_TOLERANCE_BPS}
                     THEN qty ELSE 0 END) / SUM(qty) AS vwap_tracking_share
        FROM running
        GROUP BY symbol, session, trade_date
    ),
    final_minute AS (
        SELECT symbol, trade_date,
               SUM(trade_price * qty) / SUM(qty) AS final_minute_vwap,
               SUM(qty) AS final_minute_volume
        FROM window_trades
        WHERE time_bucket >= '{SETTLEMENT_WINDOW_END[:2]}:29:00'
        GROUP BY symbol, trade_date
    ),
    open_mid AS (
        -- The book's mid at the window's open, from the reconstructed book rather than from
        -- the last trade: a stale print minutes before 15:00 is not where the market stood.
        SELECT symbol, trade_date,
               FIRST(midpoint ORDER BY snapshot_time) AS mid_at_open
        FROM read_parquet('{snaps}')
        WHERE midpoint IS NOT NULL
        GROUP BY symbol, trade_date
    )
    SELECT
        p.symbol,
        p.session,
        p.trade_date,
        p.is_expiry,
        {sql_case(column="p.symbol")},
        p.settle_vwap,
        p.window_volume,
        p.window_trades,
        p.close_price,
        o.mid_at_open,
        f.final_minute_vwap,
        f.final_minute_volume / NULLIF(p.window_volume, 0) AS final_minute_volume_share,
        p.vwap_tracking_share,
        (p.settle_vwap - o.mid_at_open) / NULLIF(o.mid_at_open, 0) * 10000.0 AS drift_bps,
        ABS((p.settle_vwap - o.mid_at_open) / NULLIF(o.mid_at_open, 0)) * 10000.0 AS abs_drift_bps,
        (p.settle_vwap - p.close_price) / NULLIF(p.close_price, 0) * 10000.0 AS reversal_bps,
        ABS((p.settle_vwap - p.close_price) / NULLIF(p.close_price, 0)) * 10000.0 AS abs_reversal_bps,
        ABS((f.final_minute_vwap - p.settle_vwap) / NULLIF(p.settle_vwap, 0)) * 10000.0
            AS terminal_gap_bps
    FROM per_session p
    LEFT JOIN open_mid o ON p.symbol = o.symbol AND p.trade_date = o.trade_date
    LEFT JOIN final_minute f ON p.symbol = f.symbol AND p.trade_date = f.trade_date
    ORDER BY p.symbol, p.trade_date
    """

    try:
        with duckdb.connect() as conn:
            result = conn.execute(query).df()
    except Exception as exc:
        logger.error(f"[S1] failed: {exc}")
        return pd.DataFrame()

    result.to_csv(out_csv, index=False)
    logger.info(f"[S1] {len(result)} symbol-sessions -> {out_csv}")
    return result


if __name__ == "__main__":
    print(run_s1_settlement_price().head(10).to_string())
