"""
a11_amihud_illiquidity.py — Amihud Illiquidity Ratio Analysis (H27) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a11_amihud_illiquidity():
    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades").replace("\\", "/")
    files = glob.glob(f"{cash_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched trades missing for A11 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A11] Calculating Amihud Illiquidity Ratio (H27) (DuckDB C++)...")

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

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a11_amihud_illiquidity.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A11 Amihud Illiquidity results to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A11 Amihud Illiquidity failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a11_amihud_illiquidity()
