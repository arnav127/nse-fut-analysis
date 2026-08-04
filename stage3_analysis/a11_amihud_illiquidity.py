"""Amihud illiquidity metric calculation (Stage 3 A11, H27)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a11_amihud_illiquidity() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched trades missing for A11 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A11] Calculating Amihud Illiquidity Metric...")

    query = f"""
    WITH min_data AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, time_bucket, is_expiry, is_settlement_window,
            SUM(trade_price * trade_quantity) AS volume_inr,
            SUM(trade_price * trade_quantity) / SUM(trade_quantity) AS vwap_price,
            ABS(LN((SUM(trade_price * trade_quantity) / SUM(trade_quantity)) / 
                   LAG(SUM(trade_price * trade_quantity) / SUM(trade_quantity)) 
                   OVER (PARTITION BY TRIM(symbol), trade_date ORDER BY time_bucket))) AS abs_return
        FROM read_parquet('{cash_path}/**/*.parquet')
        GROUP BY TRIM(symbol), trade_date, time_bucket, is_expiry, is_settlement_window
    ),
    amihud_calc AS (
        SELECT 
            symbol, trade_date, is_expiry,
            AVG(CASE WHEN is_settlement_window = True THEN abs_return / (volume_inr / 1e6 + 1e-5) ELSE NULL END) AS amihud_settlement,
            AVG(CASE WHEN is_settlement_window = False THEN abs_return / (volume_inr / 1e6 + 1e-5) ELSE NULL END) AS amihud_presettlement
        FROM min_data
        WHERE abs_return IS NOT NULL AND volume_inr > 0
        GROUP BY symbol, trade_date, is_expiry
    )
    SELECT 
        symbol, trade_date, is_expiry,
        amihud_settlement,
        amihud_presettlement,
        (amihud_settlement - amihud_presettlement) / (amihud_presettlement + 1e-8) AS amihud_uplift
    FROM amihud_calc
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a11_amihud_illiquidity.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A11 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A11 Amihud Illiquidity failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a11_amihud_illiquidity()
