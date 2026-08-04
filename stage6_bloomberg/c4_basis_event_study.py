"""Basis Event Study around settlement window start (Stage 6 C4)."""

from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import RESULTS_DIR


def run_c4_basis_event_study() -> Optional[pd.DataFrame]:
    in_csv = Path(RESULTS_DIR) / "a1_vwap_trajectory.csv"
    out_csv = Path(RESULTS_DIR) / "c4_basis_event_study.csv"

    if not in_csv.exists():
        print("[WARN] A1 VWAP trajectory missing for C4 Event Study.")
        return None

    print("[ANALYSIS C4] Computing Cumulative Abnormal Basis Event Study...")
    df = pd.read_csv(in_csv)

    grouped = df.groupby(["time_bucket", "is_expiry"])["basis_bps"].agg(["mean", "std", "count"]).reset_index()
    grouped.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C4 Basis Event Study results to {out_csv}")
    return grouped


if __name__ == "__main__":
    run_c4_basis_event_study()
