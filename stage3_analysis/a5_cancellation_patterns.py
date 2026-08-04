"""
a5_cancellation_patterns.py — Cancellation patterns and spoofing detection (H7, H8) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a5_cancellation_patterns():
    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders").replace("\\", "/")
    files = glob.glob(f"{orders_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched orders missing for A5 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A5] Analyzing Cancellation Patterns (DuckDB C++)...")

    query = f"""
    SELECT 
        symbol, trade_date, time_bucket, is_expiry, participant_type, algo_type,
        SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END) AS entries,
        SUM(CASE WHEN activity_type = 3 THEN 1 ELSE 0 END) AS cancellations,
        SUM(CASE WHEN activity_type = 4 THEN 1 ELSE 0 END) AS modifications,
        CASE 
            WHEN SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END) > 0 
            THEN SUM(CASE WHEN activity_type = 3 THEN 1 ELSE 0 END) * 1.0 / SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END)
            ELSE 0.0 
        END AS cancel_to_entry_ratio
    FROM read_parquet('{orders_path}/*/*.parquet')
    WHERE is_settlement_window = True
    GROUP BY symbol, trade_date, time_bucket, is_expiry, participant_type, algo_type
    ORDER BY symbol, trade_date, time_bucket
    """

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a5_cancellation_patterns.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A5 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A5 Cancellation Patterns failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a5_cancellation_patterns()
