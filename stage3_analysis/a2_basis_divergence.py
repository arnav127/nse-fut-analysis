"""Basis volatility, divergence metrics, and paired statistical tests (Stage 3 A2, H1-H2)."""

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from config.settings import EXPIRY_CONTROL_PAIRS, RESULTS_DIR


def run_a2_basis_divergence() -> Optional[pd.DataFrame]:
    in_csv = Path(RESULTS_DIR) / "a1_vwap_trajectory.csv"
    if not in_csv.exists():
        print("[WARN] A1 output missing for A2 analysis.")
        return None

    print("[ANALYSIS A2] Analyzing Basis Volatility & Divergence...")
    df = pd.read_csv(in_csv)

    grouped = df.groupby(["symbol", "trade_date", "is_expiry", "liquidity_group"])

    metrics = []
    for (symbol, trade_date, is_expiry, liq_group), group in grouped:
        basis_vals = group["basis_bps"].dropna()
        if basis_vals.empty:
            continue

        std_dev = np.std(basis_vals)
        mad = np.mean(np.abs(basis_vals - np.mean(basis_vals)))
        basis_range = np.ptp(basis_vals)
        terminal_shift = basis_vals.iloc[-1] - basis_vals.iloc[0] if len(basis_vals) > 1 else 0.0

        metrics.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "liquidity_group": liq_group,
            "basis_std_dev": std_dev,
            "basis_mad": mad,
            "basis_range": basis_range,
            "terminal_shift": terminal_shift,
            "max_abs_basis": np.max(np.abs(basis_vals)),
        })

    res_df = pd.DataFrame(metrics)
    out_csv = Path(RESULTS_DIR) / "a2_basis_divergence.csv"
    res_df.to_csv(out_csv, index=False)

    print("\n--- HYPOTHESIS TESTS (A2) ---")
    res_df["date_ddmmyyyy"] = pd.to_datetime(res_df["trade_date"]).dt.strftime("%d%m%Y")

    expiry_vols = []
    control_vols = []
    for exp_date, ctl_date in EXPIRY_CONTROL_PAIRS:
        exp_sub = res_df[res_df["date_ddmmyyyy"] == exp_date]
        ctl_sub = res_df[res_df["date_ddmmyyyy"] == ctl_date]
        merged_pair = exp_sub.merge(ctl_sub, on="symbol", suffixes=("_exp", "_ctl"))
        expiry_vols.extend(merged_pair["basis_std_dev_exp"].values)
        control_vols.extend(merged_pair["basis_std_dev_ctl"].values)

    if len(expiry_vols) > 1:
        t_stat, p_val = stats.ttest_rel(expiry_vols, control_vols)
        w_stat, w_pval = stats.wilcoxon(expiry_vols, control_vols)
        diffs = np.array(expiry_vols) - np.array(control_vols)
        cohen_d = np.mean(diffs) / (np.std(diffs, ddof=1) + 1e-8)

        print(f"[H1 Paired t-test] t-stat={t_stat:.4f}, p-val={p_val:.4e}, Cohen's d={cohen_d:.4f}")
        print(f"[H1 Wilcoxon Signed-Rank] W-stat={w_stat:.4f}, p-val={w_pval:.4e}")

    liquid_exp = res_df[(res_df["is_expiry"] == True) & (res_df["liquidity_group"] == "Liquid")]["basis_std_dev"]
    illiquid_exp = res_df[(res_df["is_expiry"] == True) & (res_df["liquidity_group"] == "Illiquid")]["basis_std_dev"]

    if not liquid_exp.empty and not illiquid_exp.empty:
        u_stat, p_val2 = stats.mannwhitneyu(illiquid_exp, liquid_exp)
        print(f"[H2 Mann-Whitney U] Illiquid vs Liquid Basis Vol: U-stat={u_stat:.4f}, p-val={p_val2:.4e}")

    print(f"[DONE] Saved A2 results to {out_csv}")
    return res_df


if __name__ == "__main__":
    run_a2_basis_divergence()
