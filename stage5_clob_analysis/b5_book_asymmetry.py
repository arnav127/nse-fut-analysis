"""
b5_book_asymmetry.py — Directional order book pressure & asymmetry (H18, H19) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def run_b5_book_asymmetry():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet").replace("\\", "/")
    files = glob.glob(pattern)
    if not files:
        print("[WARN] No CLOB snapshot files found for B5 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B5] Analyzing Directional Book Pressure & Asymmetry (DuckDB C++)...")
    expiry_list = ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

    query = f"""
    WITH base AS (
        SELECT 
            symbol, trade_date,
            LN((total_bid_volume + 1.0) / (total_ask_volume + 1.0)) AS log_pressure,
            book_imbalance,
            snapshot_time
        FROM read_parquet('{pattern}')
    ),
    means AS (
        SELECT symbol, trade_date, AVG(book_imbalance) AS mean_imbalance
        FROM base
        GROUP BY symbol, trade_date
    )
    SELECT 
        b.symbol,
        b.trade_date,
        (strftime(CAST(b.trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        AVG(b.log_pressure) AS mean_log_pressure,
        AVG(CASE WHEN SIGN(b.book_imbalance) = SIGN(m.mean_imbalance) THEN 1.0 ELSE 0.0 END) AS book_pressure_persistence,
        LAST(b.book_imbalance ORDER BY b.snapshot_time) AS final_imbalance
    FROM base b
    JOIN means m ON b.symbol = m.symbol AND b.trade_date = m.trade_date
    GROUP BY b.symbol, b.trade_date
    ORDER BY b.symbol, b.trade_date
    """

    conn = duckdb.connect()
    try:
        res_df = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "b5_book_asymmetry.csv")
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B5 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as e:
        print(f"[ERROR-DUCKDB] B5 Book Asymmetry failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b5_book_asymmetry()
