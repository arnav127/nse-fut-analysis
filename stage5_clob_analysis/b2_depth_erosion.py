"""
b2_depth_erosion.py — Order book depth erosion and asymmetry (H14, H15).
"""
import os
import glob
import pandas as pd
import numpy as np
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, LIQUID_SYMBOLS, EXPIRY_THURSDAYS_DDMMYYYY

def run_b2_depth_erosion():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet")
    files = glob.glob(pattern)
    if not files:
        print("[WARN] No CLOB snapshot files found for B2 analysis.")
        return

    print(f"[ANALYSIS B2] Analyzing Order Book Depth Erosion...")

    metrics = []
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue

        if df.empty:
            continue

        symbol = df["symbol"].iloc[0]
        trade_date = df["trade_date"].iloc[0]
        date_clean = pd.to_datetime(trade_date).strftime("%d%m%Y")
        is_expiry = date_clean in EXPIRY_THURSDAYS_DDMMYYYY
        liq_group = "Liquid" if symbol in LIQUID_SYMBOLS else "Illiquid"

        tot_bid = df["total_bid_volume"].mean()
        tot_ask = df["total_ask_volume"].mean()
        imbalance = df["book_imbalance"].mean()

        metrics.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "liquidity_group": liq_group,
            "avg_bid_depth": tot_bid,
            "avg_ask_depth": tot_ask,
            "avg_book_imbalance": imbalance,
            "abs_imbalance": np.abs(imbalance)
        })

    res_df = pd.DataFrame(metrics)
    out_csv = os.path.join(RESULTS_DIR, "b2_depth_erosion.csv")
    res_df.to_csv(out_csv, index=False)
    print(f"[DONE] Saved B2 results to {out_csv}")
    return res_df
