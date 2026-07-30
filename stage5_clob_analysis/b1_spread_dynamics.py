"""
b1_spread_dynamics.py — Bid-Ask spread dynamics and expansion (H12, H13).
"""
import os
import glob
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, LIQUID_SYMBOLS, EXPIRY_THURSDAYS_DDMMYYYY

def run_b1_spread_dynamics():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet")
    files = glob.glob(pattern)
    if not files:
        print("[WARN] No CLOB snapshot files found for B1 analysis.")
        return

    print(f"[ANALYSIS B1] Analyzing Bid-Ask Spread Dynamics ({len(files)} files)...")

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

        # Convert date format to ddMMyyyy for expiry check
        date_clean = pd.to_datetime(trade_date).strftime("%d%m%Y")
        is_expiry = date_clean in EXPIRY_THURSDAYS_DDMMYYYY
        liq_group = "Liquid" if symbol in LIQUID_SYMBOLS else "Illiquid"

        spreads = df["spread_bps"].dropna()
        if len(spreads) == 0:
            continue

        metrics.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "liquidity_group": liq_group,
            "mean_spread_bps": np.mean(spreads),
            "max_spread_bps": np.max(spreads),
            "min_spread_bps": np.min(spreads),
            "std_spread_bps": np.std(spreads),
            "spread_at_1500": spreads.iloc[0] if len(spreads) > 0 else np.nan,
            "spread_at_1530": spreads.iloc[-1] if len(spreads) > 0 else np.nan
        })

    res_df = pd.DataFrame(metrics)
    out_csv = os.path.join(RESULTS_DIR, "b1_spread_dynamics.csv")
    res_df.to_csv(out_csv, index=False)
    print(f"[DONE] Saved B1 results to {out_csv}")
    return res_df
