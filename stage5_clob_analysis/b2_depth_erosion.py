"""
b2_depth_erosion.py — Order book depth erosion and asymmetry (H14, H15) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, LIQUID_SYMBOLS, EXPIRY_THURSDAYS_DDMMYYYY

def run_b2_depth_erosion():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet").replace("\\", "/")
    files = glob.glob(pattern)
    if not files:
        print("[WARN] No CLOB snapshot files found for B2 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B2] Analyzing Order Book Depth Erosion ({len(files)} files via DuckDB C++)...")
    liq_list = ", ".join([f"'{s}'" for s in LIQUID_SYMBOLS])
    expiry_list = ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

    query = f"""
    WITH snap_agg AS (
        SELECT 
            symbol, trade_date,
            AVG(total_bid_volume) AS avg_bid_depth,
            AVG(total_ask_volume) AS avg_ask_depth,
            AVG(book_imbalance) AS avg_book_imbalance
        FROM read_parquet('{pattern}')
        GROUP BY symbol, trade_date
    )
    SELECT 
        symbol,
        trade_date,
        (strftime(CAST(trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        CASE WHEN symbol IN ({liq_list}) THEN 'Liquid' ELSE 'Illiquid' END AS liquidity_group,
        avg_bid_depth,
        avg_ask_depth,
        avg_book_imbalance,
        ABS(avg_book_imbalance) AS abs_imbalance
    FROM snap_agg
    ORDER BY symbol, trade_date
    """

    conn = duckdb.connect()
    try:
        res_df = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "b2_depth_erosion.csv")
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B2 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as e:
        print(f"[ERROR-DUCKDB] B2 Depth Erosion failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b2_depth_erosion()
