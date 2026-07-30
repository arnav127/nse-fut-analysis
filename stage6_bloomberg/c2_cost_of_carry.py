"""
c2_cost_of_carry.py — Fair value basis and mispricing analysis.
"""
import os
import pandas as pd
from config.settings import RESULTS_DIR
from stage6_bloomberg.load_bloomberg_data import load_cost_of_carry

def run_c2_cost_of_carry():
    print("[ANALYSIS C2] Analyzing Cost of Carry & Mispricing...")
    df_coc = load_cost_of_carry()
    out_csv = os.path.join(RESULTS_DIR, "c2_cost_of_carry.csv")

    if df_coc.empty:
        df_res = pd.DataFrame(columns=["symbol", "date", "actual_basis", "theoretical_basis", "mispricing_bps"])
        df_res.to_csv(out_csv, index=False)
        print(f"[DONE] Saved C2 results to {out_csv}")
        return df_res

    # Calculate theoretical basis & mispricing
    r = 0.06 # 6% risk-free rate proxy
    df_coc["theoretical_basis"] = df_coc["spot_close"] * r * (df_coc["days_to_expiry"] / 365.0)
    df_coc["mispricing_bps"] = ((df_coc["actual_basis"] - df_coc["theoretical_basis"]) / df_coc["spot_close"]) * 10000.0

    df_coc.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C2 results to {out_csv}")
    return df_coc
