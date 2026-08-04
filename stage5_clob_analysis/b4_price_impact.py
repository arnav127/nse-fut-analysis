"""Per-trade price impact analysis & Kyle's Lambda estimation (Stage 5 B4, H11-H12)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import CLOB_DATA_DIR, ENRICHED_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR


def run_b4_price_impact() -> pd.DataFrame:
    print("[ANALYSIS B4] Calculating Per-Trade Price Impact & Kyle's Lambda...")
    
    clob_pattern = str(Path(CLOB_DATA_DIR) / "**" / "*.parquet").replace("\\", "/")
    trades_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    out_csv = Path(RESULTS_DIR) / "b4_price_impact.csv"

    if not glob.glob(clob_pattern, recursive=True) or not glob.glob(f"{trades_path}/**/*.parquet", recursive=True):
        print("[WARN] No CLOB snapshot files found for B4 analysis.")
        df_res = pd.DataFrame(columns=[
            "symbol", "trade_date", "is_expiry", "mean_price_impact_bps",
            "median_price_impact_bps", "kyle_lambda", "kyle_r2"
        ])
        df_res.to_csv(out_csv, index=False)
        return df_res

    expiry_list = ", ".join(f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    query = f"""
    WITH trade_deltas AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date,
            ABS(trade_price - LAG(trade_price) OVER (PARTITION BY TRIM(symbol), trade_date ORDER BY txn_time_jiffies)) / (trade_price + 1e-5) * 10000.0 AS impact_bps,
            (trade_price - LAG(trade_price) OVER (PARTITION BY TRIM(symbol), trade_date ORDER BY txn_time_jiffies)) AS px_change,
            trade_quantity AS qty
        FROM read_parquet('{trades_path}/**/*.parquet')
        WHERE is_settlement_window = True
    )
    SELECT 
        symbol,
        trade_date,
        (CAST(trade_date AS VARCHAR) IN ({expiry_list}) OR strftime(try_cast(trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        AVG(impact_bps) AS mean_price_impact_bps,
        MEDIAN(impact_bps) AS median_price_impact_bps,
        COVAR_SAMP(px_change, qty) / (VAR_SAMP(qty) + 1e-12) AS kyle_lambda,
        POWER(CORR(px_change, qty), 2) AS kyle_r2
    FROM trade_deltas
    WHERE impact_bps IS NOT NULL
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
