"""
a9_trade_clustering.py — Trade Size Distribution & Concentration (H25) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a9_trade_clustering():
    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades").replace("\\", "/")
    files = glob.glob(f"{cash_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched trades missing for A9 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A9] Analyzing Trade Size Concentration & Clustering (H25) (DuckDB C++)...")

    query = f"""
    SELECT 
        symbol, trade_date, is_expiry,
        SUM(trade_quantity) AS tot_vol,
        COUNT(*) AS trade_cnt,
        MAX(trade_quantity) AS max_trade_qty,
        AVG(trade_quantity) AS avg_trade_qty,
        SUM(trade_quantity * trade_quantity) AS sum_sq_qty,
        SUM(trade_quantity * trade_quantity) * 1.0 / (SUM(trade_quantity) * SUM(trade_quantity) + 1e-5) AS hhi_concentration,
        MAX(trade_quantity) * 1.0 / (AVG(trade_quantity) + 1e-5) AS max_to_avg_ratio
    FROM read_parquet('{cash_path}/*/*.parquet')
    WHERE is_settlement_window = True
    GROUP BY symbol, trade_date, is_expiry
    ORDER BY symbol, trade_date
    """

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a9_trade_clustering.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A9 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A9 Trade Clustering failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a9_trade_clustering()
