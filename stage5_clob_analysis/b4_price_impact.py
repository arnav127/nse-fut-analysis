"""Per-trade price impact analysis & Kyle's Lambda estimation (Stage 5 B4, H11-H12)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR
from utils.paths import session_to_iso


def run_b4_price_impact() -> pd.DataFrame:
    print("[ANALYSIS B4] Calculating Per-Trade Price Impact & Kyle's Lambda...")
    
    # This analysis reads the trade tape only. It used to also require CLOB snapshots to
    # exist before running, which it never read - so it reported "no CLOB snapshot files"
    # and wrote an empty result whenever stage 4 had not run, for a measurement that does
    # not depend on stage 4 at all.
    trades_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    out_csv = Path(RESULTS_DIR) / "b4_price_impact.csv"

    if not glob.glob(f"{trades_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched cash trades missing for B4 analysis.")
        df_res = pd.DataFrame(columns=[
            "symbol", "trade_date", "is_expiry", "n_trades", "n_minutes",
            "mean_price_impact_bps", "median_price_impact_bps", "kyle_lambda", "kyle_r2"
        ])
        df_res.to_csv(out_csv, index=False)
        return df_res

    # The snapshot layer stores `trade_date` as ISO, derived from the record timestamp.
    # The expiry calendar is written the way NSE names its files, so it is converted here;
    # comparing the two spellings directly matched nothing and reported every session as a
    # control day.
    expiry_list = ", ".join(f"'{session_to_iso(d)}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    # Kyle's lambda is estimated on minute buckets, not on individual trades.
    #
    # The previous version regressed the trade-to-trade price change on raw traded quantity.
    # Quantity is unsigned, so buys and sells of the same size contribute price changes of
    # opposite sign to the same regressor: the covariance cancels and lambda comes out at
    # roughly zero for every symbol on every session, with an r-squared to match. The number
    # was not small because impact was small - it was small because the regressor carried no
    # direction.
    #
    # Direction comes from the tick rule: a trade above the previous trade price is buyer
    # initiated, below is seller initiated, and an unchanged price inherits the last
    # non-zero direction. Signed volume is then summed over the minute and the minute's
    # price change regressed on it, which is Kyle's lambda as it is normally estimated on
    # trade data. Bucketing also removes the mechanical link between signing a trade by its
    # own price change and then explaining that same price change.
    query = f"""
    WITH ticks AS (
        SELECT
            symbol, trade_date, time_bucket, txn_datetime, trade_price, trade_quantity,
            trade_price - LAG(trade_price) OVER w AS tick_change
        FROM read_parquet('{trades_path}/**/*.parquet')
        WHERE is_settlement_window AND is_regular_market
        WINDOW w AS (PARTITION BY symbol, trade_date ORDER BY txn_datetime)
    ),
    signed AS (
        SELECT
            symbol, trade_date, time_bucket, txn_datetime, trade_price, trade_quantity,
            tick_change,
            ABS(tick_change) / NULLIF(trade_price - tick_change, 0) * 10000.0 AS impact_bps,
            -- Zero-tick trades carry the last non-zero direction forward, which is the
            -- standard tick-rule convention; a run of same-price trades is one side
            -- working through resting depth, not a sequence of unsigned trades.
            COALESCE(
                LAST_VALUE(CASE WHEN tick_change > 0 THEN 1 WHEN tick_change < 0 THEN -1 END
                           IGNORE NULLS) OVER (
                    PARTITION BY symbol, trade_date ORDER BY txn_datetime
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
                0) AS trade_sign
        FROM ticks
    ),
    minute AS (
        SELECT
            symbol, trade_date, time_bucket,
            SUM(trade_sign * CAST(trade_quantity AS DOUBLE)) AS signed_volume,
            AVG(impact_bps) AS mean_impact_bps,
            MEDIAN(impact_bps) AS median_impact_bps,
            COUNT(*) AS n_trades,
            LAST(trade_price ORDER BY txn_datetime)
                - FIRST(trade_price ORDER BY txn_datetime) AS px_change
        FROM signed
        GROUP BY symbol, trade_date, time_bucket
    )
    SELECT
        symbol,
        trade_date,
        trade_date IN ({expiry_list}) AS is_expiry,
        SUM(n_trades) AS n_trades,
        COUNT(*) AS n_minutes,
        SUM(mean_impact_bps * n_trades) / NULLIF(SUM(n_trades), 0) AS mean_price_impact_bps,
        MEDIAN(median_impact_bps) AS median_price_impact_bps,
        COVAR_SAMP(px_change, signed_volume)
            / NULLIF(VAR_SAMP(signed_volume), 0) AS kyle_lambda,
        POWER(CORR(px_change, signed_volume), 2) AS kyle_r2
    FROM minute
    GROUP BY symbol, trade_date
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            df_res = conn.execute(query).df()
        df_res.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B4 results ({len(df_res)} rows) to {out_csv}")
        return df_res
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B4 Price Impact failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b4_price_impact()
