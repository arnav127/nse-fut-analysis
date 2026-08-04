"""
b6_volume_profile.py — Settlement Volume Profile & Gini Concentration (H29) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def _gini_coefficient(x):
    """Compute Gini coefficient of array x."""
    x = np.asarray(x, dtype=np.float64)
    if np.amin(x) < 0:
        x -= np.amin(x)
    x += 1e-7
    x = np.sort(x)
    n = x.size
    index = np.arange(1, n + 1)
    return (np.sum((2 * index - n - 1) * x)) / (n * np.sum(x))

def run_b6_volume_profile():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet").replace("\\", "/")
    files = glob.glob(pattern)
    out_csv = os.path.join(RESULTS_DIR, "b6_volume_profile.csv")

    if not files:
        print("[WARN] No CLOB snapshot files found for B6 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B6] Analyzing Settlement Volume Profile & Gini Index (H29) (DuckDB C++)...")
    expiry_list = ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

    query = f"""
    SELECT 
        symbol,
        trade_date,
        (strftime(CAST(trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        seconds_from_1500,
        AVG(total_bid_volume + total_ask_volume) AS tot_vol
    FROM read_parquet('{pattern}')
    WHERE total_bid_volume IS NOT NULL
    GROUP BY symbol, trade_date, is_expiry, seconds_from_1500
    ORDER BY symbol, trade_date, seconds_from_1500
    """

    conn = duckdb.connect()
    try:
        df_mins = conn.execute(query).df()
        metrics = []
        for (symbol, trade_date, is_expiry), grp in df_mins.groupby(["symbol", "trade_date", "is_expiry"]):
            vol_vals = grp["tot_vol"].values
            if len(vol_vals) < 5:
                continue
            gini_val = _gini_coefficient(vol_vals)
            metrics.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "volume_gini": gini_val,
                "peak_to_trough_ratio": np.max(vol_vals) / (np.min(vol_vals) + 1e-5),
                "final_min_share": vol_vals[-1] / (np.sum(vol_vals) + 1e-5)
            })

        res_df = pd.DataFrame(metrics)
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B6 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as e:
        print(f"[ERROR-DUCKDB] B6 Volume Profile failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b6_volume_profile()
