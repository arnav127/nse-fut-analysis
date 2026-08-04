"""
b7_market_resilience.py — Order Book Resilience & Post-Shock Recovery Time (H30) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def run_b7_market_resilience():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet").replace("\\", "/")
    files = glob.glob(pattern)
    out_csv = os.path.join(RESULTS_DIR, "b7_market_resilience.csv")

    if not files:
        print("[WARN] No CLOB snapshot files found for B7 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B7] Analyzing Market Resilience & Recovery Time (H30) (DuckDB C++)...")
    expiry_list = ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

    query = f"""
    SELECT 
        symbol,
        trade_date,
        (strftime(CAST(trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        snapshot_time,
        spread_bps
    FROM read_parquet('{pattern}')
    WHERE spread_bps IS NOT NULL
    ORDER BY symbol, trade_date, snapshot_time
    """

    conn = duckdb.connect()
    try:
        df_all = conn.execute(query).df()
        metrics = []
        for (symbol, trade_date, is_expiry), grp in df_all.groupby(["symbol", "trade_date", "is_expiry"]):
            spreads = grp["spread_bps"].values
            if len(spreads) < 20:
                continue

            baseline_spread = np.mean(spreads)
            shock_threshold = baseline_spread * 2.0
            shock_indices = np.where(spreads > shock_threshold)[0]
            recovery_times = []

            for idx in shock_indices:
                recovered = np.where(spreads[idx:] <= baseline_spread * 1.5)[0]
                if len(recovered) > 0:
                    recovery_times.append(recovered[0])

            avg_recovery = np.mean(recovery_times) if recovery_times else 0.0
            metrics.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "n_shocks": len(shock_indices),
                "mean_recovery_time_sec": avg_recovery
            })

        res_df = pd.DataFrame(metrics)
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B7 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as e:
        print(f"[ERROR-DUCKDB] B7 Market Resilience failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b7_market_resilience()
