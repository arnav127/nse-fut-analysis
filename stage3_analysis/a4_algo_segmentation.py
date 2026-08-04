"""Algorithmic vs Non-Algorithmic order flow segmentation (Stage 3 A4, H15-H16)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a4_algo_segmentation() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/*/*.parquet"):
        print("[WARN] Enriched orders missing for A4 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A4] Analyzing Algo vs Non-Algo Segmentation...")

    query = f"""
    SELECT 
        symbol, trade_date, is_expiry, is_settlement_window, algo_type,
        COUNT(*) AS total_orders,
        SUM(volume_original) AS total_volume,
        SUM(CASE WHEN ioc_flag = 'Y' THEN 1 ELSE 0 END) AS ioc_orders,
        SUM(CASE WHEN mkt_order_flag = 'Y' THEN 1 ELSE 0 END) AS market_orders,
        SUM(CASE WHEN ioc_flag = 'Y' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS ioc_rate,
        SUM(CASE WHEN mkt_order_flag = 'Y' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS mkt_rate
    FROM read_parquet('{orders_path}/*/*.parquet')
    WHERE activity_type = 1
    GROUP BY symbol, trade_date, is_expiry, is_settlement_window, algo_type
    ORDER BY symbol, trade_date, algo_type
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a4_algo_segmentation.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A4 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A4 Algo Segmentation failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a4_algo_segmentation()
