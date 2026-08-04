"""
b3_order_flow_imbalance.py — Order Flow Imbalance (OFI) analysis (H16) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_b3_order_flow_imbalance():
    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders").replace("\\", "/")
    files = glob.glob(f"{orders_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched orders missing for B3 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS B3] Computing Order Flow Imbalance (OFI) (DuckDB C++)...")

    query = f"""
    WITH base AS (
        SELECT 
            symbol, trade_date, time_bucket, is_expiry,
            SUM(CASE WHEN buy_sell = 'B' THEN volume_original ELSE 0 END) AS buy_volume,
            SUM(CASE WHEN buy_sell = 'S' THEN volume_original ELSE 0 END) AS sell_volume
        FROM read_parquet('{orders_path}/*/*.parquet')
        WHERE is_settlement_window = True AND activity_type = 1
        GROUP BY symbol, trade_date, time_bucket, is_expiry
    )
    SELECT 
        symbol, trade_date, time_bucket, is_expiry,
        buy_volume, sell_volume,
        (buy_volume - sell_volume) * 1.0 / (buy_volume + sell_volume + 1e-5) AS cash_ofi
    FROM base
    ORDER BY symbol, trade_date, time_bucket
    """

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "b3_order_flow_imbalance.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B3 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] B3 Order Flow Imbalance failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b3_order_flow_imbalance()
