"""
c4_basis_event_study.py — Basis Event Study around 15:00 Settlement Window Start.
"""
import os
import pandas as pd
import numpy as np
from config.settings import RESULTS_DIR

def run_c4_basis_event_study():
    in_csv = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    out_csv = os.path.join(RESULTS_DIR, "c4_basis_event_study.csv")

    if not os.path.exists(in_csv):
        print("[WARN] A1 VWAP trajectory missing for C4 Event Study.")
        return

    print("[ANALYSIS C4] Computing Cumulative Abnormal Basis Event Study...")
    df = pd.read_csv(in_csv)

    # Event window: 15:00 is t=0
    # Baseline window: pre-15:00 or first 5 minutes of settlement
    grouped = df.groupby(["time_bucket", "is_expiry"])["basis_bps"].agg(["mean", "std", "count"]).reset_index()
    grouped.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C4 Basis Event Study results to {out_csv}")
    return grouped
