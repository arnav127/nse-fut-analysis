"""Order lifespan and phantom order detection (<1s cancellations) (Stage 3 A12, H28)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a12_order_lifespan() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched orders missing for A12 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A12] Calculating Order Lifespan & Phantom Orders (<1s)...")

    query = f"""
    WITH order_lifecycle AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, is_expiry, order_number, participant_type, algo_type,
            MIN(CASE WHEN activity_type = 1 THEN txn_time_jiffies ELSE NULL END) AS entry_jiffies,
            MIN(CASE WHEN activity_type = 3 THEN txn_time_jiffies ELSE NULL END) AS cancel_jiffies
        FROM read_parquet('{orders_path}/**/*.parquet')
        WHERE is_settlement_window = True
        GROUP BY TRIM(symbol), trade_date, is_expiry, order_number, participant_type, algo_type
    ),
    lifespan_calc AS (
        SELECT 
            symbol, trade_date, is_expiry, participant_type, algo_type,
            (cancel_jiffies - entry_jiffies) / 65536.0 AS lifespan_seconds
        FROM order_lifecycle
        WHERE entry_jiffies IS NOT NULL AND cancel_jiffies IS NOT NULL AND cancel_jiffies >= entry_jiffies
    )
    SELECT 
        symbol, trade_date, is_expiry, participant_type, algo_type,
        COUNT(*) AS cancelled_orders,
        AVG(lifespan_seconds) AS mean_lifespan_sec,
        MEDIAN(lifespan_seconds) AS median_lifespan_sec,
        SUM(CASE WHEN lifespan_seconds < 1.0 THEN 1 ELSE 0 END) AS phantom_orders,
        SUM(CASE WHEN lifespan_seconds < 1.0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS phantom_order_rate
    FROM lifespan_calc
    GROUP BY symbol, trade_date, is_expiry, participant_type, algo_type
    ORDER BY symbol, trade_date, participant_type
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a12_order_lifespan.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A12 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A12 Order Lifespan failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a12_order_lifespan()
