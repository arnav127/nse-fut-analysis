"""
b7_market_resilience.py — Order Book Resilience & Post-Shock Recovery Time (H30).
"""
import os
import glob
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def run_b7_market_resilience():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet")
    files = glob.glob(pattern)
    out_csv = os.path.join(RESULTS_DIR, "b7_market_resilience.csv")

    if not files:
        print("[WARN] No CLOB snapshot files found for B7 analysis.")
        return

    print(f"[ANALYSIS B7] Analyzing Market Resilience & Recovery Time (H30)...")

    metrics = []
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue

        if df.empty or "spread_bps" not in df.columns:
            continue

        symbol = df["symbol"].iloc[0]
        trade_date = df["trade_date"].iloc[0]
        date_clean = pd.to_datetime(trade_date).strftime("%d%m%Y")
        is_expiry = date_clean in EXPIRY_THURSDAYS_DDMMYYYY

        spreads = df["spread_bps"].fillna(method="ffill").values
        if len(spreads) < 20:
            continue

        baseline_spread = np.mean(spreads)
        shock_threshold = baseline_spread * 2.0

        # Identify shock indices
        shock_indices = np.where(spreads > shock_threshold)[0]
        recovery_times = []

        for idx in shock_indices:
            # Find seconds to recover back to 1.5x baseline
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
    print(f"[DONE] Saved B7 Market Resilience results to {out_csv}")
    return res_df
