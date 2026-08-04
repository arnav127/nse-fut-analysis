"""
a12_order_lifespan.py — Order Lifespan & Phantom Order Detection (H28) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a12_order_lifespan():
    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders").replace("\\", "/")
    files = glob.glob(f"{orders_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched orders missing for A12 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A12] Analyzing Order Lifespan & Phantom Orders (H28) (DuckDB C++)...")

    query = f"""
    WITH order_times AS (
        SELECT 
            symbol, trade_date, is_expiry, participant_type, order_number,
            MIN(CASE WHEN activity_type = 1 THEN txn_time_jiffies END) AS entry_jiffies,
            MIN(CASE WHEN activity_type = 3 THEN txn_time_jiffies END) AS cancel_jiffies
        FROM read_parquet('{orders_path}/*/*.parquet')
        WHERE is_settlement_window = True AND activity_type IN (1, 3)
        GROUP BY symbol, trade_date, is_expiry, participant_type, order_number
        HAVING MIN(CASE WHEN activity_type = 3 THEN txn_time_jiffies END) IS NOT NULL
           AND MIN(CASE WHEN activity_type = 1 THEN txn_time_jiffies END) IS NOT NULL
    ),
    lifespans AS (
        SELECT 
            symbol, trade_date, is_expiry, participant_type,
            (cancel_jiffies - entry_jiffies) / 65536.0 AS lifespan_seconds,
            ((cancel_jiffies - entry_jiffies) / 65536.0 < 1.0) AS is_phantom
        FROM order_times
    )
    SELECT 
        symbol, trade_date, is_expiry, participant_type,
        COUNT(*) AS total_cancelled_orders,
        SUM(CASE WHEN is_phantom THEN 1 ELSE 0 END) AS phantom_orders,
        AVG(lifespan_seconds) AS avg_lifespan_sec,
        SUM(CASE WHEN is_phantom THEN 1 ELSE 0 END) * 1.0 / (COUNT(*) + 1e-5) AS phantom_order_rate
    FROM lifespans
    GROUP BY symbol, trade_date, is_expiry, participant_type
    ORDER BY symbol, trade_date, participant_type
    """

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a12_order_lifespan.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A12 Order Lifespan results to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A12 Order Lifespan failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a12_order_lifespan()
