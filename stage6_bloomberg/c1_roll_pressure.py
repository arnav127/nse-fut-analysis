"""
c1_roll_pressure.py — Long/Short roll pressure calculation from Bloomberg spread & OI data.
"""
import os
import pandas as pd
import numpy as np
from config.settings import RESULTS_DIR
from stage6_bloomberg.load_bloomberg_data import build_bloomberg_master

def run_c1_roll_pressure():
    print("[ANALYSIS C1] Calculating Bloomberg Roll Pressure Direction...")
    df_bbg = build_bloomberg_master()

    out_csv = os.path.join(RESULTS_DIR, "c1_roll_pressure.csv")

    if df_bbg.empty:
        print("[WARN] Bloomberg master data empty. Creating placeholder C1 output.")
        df_res = pd.DataFrame(columns=["symbol", "expiry_date", "roll_direction_score", "predicted_punch_direction", "roll_intensity"])
        df_res.to_csv(out_csv, index=False)
        return df_res

    # Logic for roll direction score based on calendar spread & OI
    results = []
    # Process by symbol & expiry
    # Placeholder roll classification logic
    df_res = pd.DataFrame(results, columns=["symbol", "expiry_date", "roll_direction_score", "predicted_punch_direction", "roll_intensity"])
    df_res.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C1 results to {out_csv}")
    return df_res
