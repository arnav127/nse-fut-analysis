"""Amihud Illiquidity Ratio Analysis across settlement windows (Stage 3 A11, H27)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a11_amihud_illiquidity() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/*/*.parquet"):
        print("[WARN] Enriched trades missing for A11 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A11] Calculating Amihud Illiquidity Ratio (H27)...")

    query = f"""
    WITH min_agg AS (
        SELECT 
            symbol, trade_date, time_bucket, is_expiry, is_settlement_window,
            FIRST(trade_price ORDER BY txn_time_jiffies) AS first_price,
            LAST(trade_price ORDER BY txn_time_jiffies) AS last_price,
            SUM(trade_price * trade_quantity) AS traded_value
        FROM read_parquet('{cash_path}/*/*.parquet')
        GROUP BY symbol, trade_date, time_bucket, is_expiry, is_settlement_window
    ),
    amihud_min AS (
        SELECT 
            symbol, trade_date, time_bucket, is_expiry, is_settlement_window,
            ABS((last_price - first_price) / (first_price + 1e-5)) / (traded_value + 1.0) AS amihud_ratio
        FROM min_agg
    )
    SELECT 
        symbol, trade_date, is_expiry,
        AVG(CASE WHEN is_settlement_window = True THEN amihud_ratio END) AS amihud_settlement,
        AVG(CASE WHEN is_settlement_window = False THEN amihud_ratio END) AS amihud_pre_settlement,
        AVG(CASE WHEN is_settlement_window = True THEN amihud_ratio END) / 
            (AVG(CASE WHEN is_settlement_window = False THEN amihud_ratio END) + 1e-12) AS amihud_uplift
    FROM amihud_min
    GROUP BY symbol, trade_date, is_expiry
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a11_amihud_illiquidity.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A11 Amihud Illiquidity results to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A11 Amihud Illiquidity failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a11_amihud_illiquidity()
