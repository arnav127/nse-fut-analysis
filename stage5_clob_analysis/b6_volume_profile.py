"""
b6_volume_profile.py — Settlement Volume Profile & Gini Concentration (H29).
"""
import os
import glob
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
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet")
    files = glob.glob(pattern)
    out_csv = os.path.join(RESULTS_DIR, "b6_volume_profile.csv")

    if not files:
        print("[WARN] No CLOB snapshot files found for B6 analysis.")
        return

    print(f"[ANALYSIS B6] Analyzing Settlement Volume Profile & Gini Index (H29)...")

    metrics = []
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue

        if df.empty or "total_bid_volume" not in df.columns:
            continue

        symbol = df["symbol"].iloc[0]
        trade_date = df["trade_date"].iloc[0]
        date_clean = pd.to_datetime(trade_date).strftime("%d%m%Y")
        is_expiry = date_clean in EXPIRY_THURSDAYS_DDMMYYYY

        # Minute-level volume changes
        df["tot_vol"] = df["total_bid_volume"] + df["total_ask_volume"]
        vol_by_min = df.groupby("seconds_from_1500")["tot_vol"].mean().values

        if len(vol_by_min) < 5:
            continue

        gini_val = _gini_coefficient(vol_by_min)

        metrics.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "volume_gini": gini_val,
            "max_to_mean_vol_ratio": np.max(vol_by_min) / (np.mean(vol_by_min) + 1e-5)
        })

    res_df = pd.DataFrame(metrics)
    res_df.to_csv(out_csv, index=False)
    print(f"[DONE] Saved B6 Volume Profile results to {out_csv}")
    return res_df
