"""
a2_basis_divergence.py — Basis volatility, divergence metrics, and statistical tests (H1, H2).
"""
import os
import pandas as pd
import numpy as np
from scipy import stats
from config.settings import RESULTS_DIR

def run_a2_basis_divergence():
    in_csv = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    if not os.path.exists(in_csv):
        print("[WARN] A1 output missing for A2 analysis.")
        return

    print("[ANALYSIS A2] Analyzing Basis Volatility & Divergence...")
    df = pd.read_csv(in_csv)

    # Group by symbol, trade_date, is_expiry, liquidity_group
    grouped = df.groupby(["symbol", "trade_date", "is_expiry", "liquidity_group"])

    metrics = []
    for (symbol, trade_date, is_expiry, liq_group), group in grouped:
        basis_vals = group["basis_bps"].dropna()
        if len(basis_vals) == 0:
            continue

        std_dev = np.std(basis_vals)
        mad = np.mean(np.abs(basis_vals - np.mean(basis_vals)))
        basis_range = np.ptp(basis_vals)
        terminal_shift = basis_vals.iloc[-1] - basis_vals.iloc[0] if len(basis_vals) > 1 else 0

        metrics.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "liquidity_group": liq_group,
            "basis_std_dev": std_dev,
            "basis_mad": mad,
            "basis_range": basis_range,
            "terminal_shift": terminal_shift,
            "max_abs_basis": np.max(np.abs(basis_vals))
        })

    res_df = pd.DataFrame(metrics)
    out_csv = os.path.join(RESULTS_DIR, "a2_basis_divergence.csv")
    res_df.to_csv(out_csv, index=False)

    # Statistical Tests
    expiry_vol = res_df[res_df["is_expiry"] == True]["basis_std_dev"]
    control_vol = res_df[res_df["is_expiry"] == False]["basis_std_dev"]

    print("\n--- HYPOTHESIS TESTS (A2) ---")
    if len(expiry_vol) > 0 and len(control_vol) > 0:
        t_stat, p_val = stats.ttest_ind(expiry_vol, control_vol)
        print(f"[H1] Basis Volatility Expiry vs Control: t-stat={t_stat:.4f}, p-val={p_val:.4e}")

    liquid_exp = res_df[(res_df["is_expiry"] == True) & (res_df["liquidity_group"] == "Liquid")]["basis_std_dev"]
    illiquid_exp = res_df[(res_df["is_expiry"] == True) & (res_df["liquidity_group"] == "Illiquid")]["basis_std_dev"]

    if len(liquid_exp) > 0 and len(illiquid_exp) > 0:
        t_stat2, p_val2 = stats.ttest_ind(illiquid_exp, liquid_exp)
        print(f"[H2] Illiquid vs Liquid Basis Vol on Expiry: t-stat={t_stat2:.4f}, p-val={p_val2:.4e}")

    print(f"[DONE] Saved A2 results to {out_csv}")
    return res_df
