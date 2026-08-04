"""Immediate-Or-Cancel (IOC) and Market order execution aggressiveness (Stage 3 A7)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a7_ioc_aggressiveness() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched orders missing for A7 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A7] Analyzing IOC Aggressiveness & Market Orders...")

    query = f"""
    WITH base AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, time_bucket, is_expiry,
            CASE WHEN EXTRACT(MINUTE FROM txn_datetime) >= 25 THEN 'Late' ELSE 'Early' END AS sub_window,
            (ioc_flag = 'Y') AS is_ioc,
            (mkt_order_flag = 'Y') AS is_mkt
        FROM read_parquet('{orders_path}/**/*.parquet')
        WHERE is_settlement_window = True AND activity_type = 1
    )
    SELECT 
        symbol, trade_date, time_bucket, sub_window, is_expiry,
        COUNT(*) AS total_orders,
        SUM(CASE WHEN is_ioc THEN 1 ELSE 0 END) AS ioc_orders,
        SUM(CASE WHEN is_mkt THEN 1 ELSE 0 END) AS market_orders,
        SUM(CASE WHEN is_ioc THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS ioc_ratio,
        SUM(CASE WHEN is_mkt THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS mkt_ratio,
        (SUM(CASE WHEN is_ioc THEN 1 ELSE 0 END) + SUM(CASE WHEN is_mkt THEN 1 ELSE 0 END)) * 1.0 / COUNT(*) AS aggressive_ratio
    FROM base
    GROUP BY symbol, trade_date, time_bucket, sub_window, is_expiry
    ORDER BY symbol, trade_date, time_bucket
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a7_ioc_aggressiveness.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A7 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A7 IOC Aggressiveness failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a7_ioc_aggressiveness()
