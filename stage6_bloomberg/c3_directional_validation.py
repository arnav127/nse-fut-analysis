"""
c3_directional_validation.py — Directional validation: Bloomberg roll vs. NSE microstructure (H20-H23).
"""
import os
import pandas as pd
import numpy as np
from scipy import stats
from config.settings import RESULTS_DIR

def run_c3_directional_validation():
    print("[ANALYSIS C3] Cross-Referencing Bloomberg Roll Direction with NSE Microstructure...")

    c1_file = os.path.join(RESULTS_DIR, "c1_roll_pressure.csv")
    a1_file = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    b5_file = os.path.join(RESULTS_DIR, "b5_book_asymmetry.csv")
    b3_file = os.path.join(RESULTS_DIR, "b3_order_flow_imbalance.csv")

    out_csv = os.path.join(RESULTS_DIR, "c3_directional_validation.csv")

    if not os.path.exists(c1_file):
        print("[WARN] Bloomberg C1 output missing for C3 validation.")
        df_res = pd.DataFrame()
        df_res.to_csv(out_csv, index=False)
        return df_res

    df_c1 = pd.read_csv(c1_file)

    # Load VWAP drift from A1 if available
    df_vwap = pd.read_csv(a1_file) if os.path.exists(a1_file) else pd.DataFrame()
    df_b5 = pd.read_csv(b5_file) if os.path.exists(b5_file) else pd.DataFrame()
    df_b3 = pd.read_csv(b3_file) if os.path.exists(b3_file) else pd.DataFrame()

    results = []

    cols_c1 = ["symbol", "expiry_date", "predicted_punch_direction", "roll_intensity", "roll_direction_score"]
    for r in df_c1[cols_c1].itertuples(index=False):
        symbol = r.symbol
        exp_date = r.expiry_date
        pred_dir = r.predicted_punch_direction
        intensity = r.roll_intensity

        vwap_drift_bps = 0.0
        book_imbalance = 0.0
        ofi = 0.0

        # Extract actual VWAP terminal drift from A1
        if not df_vwap.empty:
            sub = df_vwap[(df_vwap["symbol"] == symbol) & (df_vwap["trade_date"] == exp_date)]
            if len(sub) > 1:
                sub = sub.sort_values("time_bucket")
                vwap_start = sub["cash_cum_vwap"].iloc[0]
                vwap_end = sub["cash_cum_vwap"].iloc[-1]
                if vwap_start > 0:
                    vwap_drift_bps = ((vwap_end - vwap_start) / vwap_start) * 10000.0

        # Extract book asymmetry from B5
        if not df_b5.empty:
            sub = df_b5[(df_b5["symbol"] == symbol) & (df_b5["trade_date"] == exp_date)]
            if not sub.empty:
                book_imbalance = sub["final_imbalance"].iloc[0]

        # Extract OFI from B3
        if not df_b3.empty:
            sub = df_b3[(df_b3["symbol"] == symbol) & (df_b3["trade_date"] == exp_date)]
            if not sub.empty:
                ofi = sub["cash_ofi"].mean()

        actual_vwap_dir = "DOWN" if vwap_drift_bps < 0 else "UP"
        actual_book_dir = "DOWN" if book_imbalance < 0 else "UP"
        actual_ofi_dir = "DOWN" if ofi < 0 else "UP"

        match_vwap = 1 if (pred_dir == actual_vwap_dir) else 0
        match_book = 1 if (pred_dir == actual_book_dir) else 0
        match_ofi = 1 if (pred_dir == actual_ofi_dir) else 0

        results.append({
            "symbol": symbol,
            "trade_date": exp_date,
            "roll_direction_score": r.roll_direction_score,
            "roll_intensity": intensity,
            "predicted_punch_dir": pred_dir,
            "vwap_drift_bps": vwap_drift_bps,
            "actual_vwap_drift_dir": actual_vwap_dir,
            "match_vwap": match_vwap,
            "book_imbalance": book_imbalance,
            "match_book": match_book,
            "ofi": ofi,
            "match_ofi": match_ofi
        })

    df_res = pd.DataFrame(results)
    df_res.to_csv(out_csv, index=False)

    print("\n--- HYPOTHESIS TESTS (C3 Directional Validation) ---")
    if not df_res.empty:
        vwap_matches = df_res["match_vwap"].sum()
        n_obs = len(df_res)
        # H20: Binomial test for VWAP direction match rate > 50%
        binom_res = stats.binomtest(vwap_matches, n_obs, p=0.5, alternative="greater")
        print(f"[H20 Binomial Test] VWAP Direction Match Rate: {vwap_matches}/{n_obs} ({vwap_matches/n_obs*100:.1f}%), p-val={binom_res.pvalue:.4e}")

        # H21: Spearman correlation between roll intensity and |vwap_drift_bps|
        if df_res["roll_intensity"].nunique() > 1 and df_res["vwap_drift_bps"].nunique() > 1:
            rho, rho_p = stats.spearmanr(df_res["roll_intensity"], np.abs(df_res["vwap_drift_bps"]))
        else:
            rho, rho_p = np.nan, np.nan
        print(f"[H21 Spearman Correlation] Roll Intensity vs |VWAP Drift|: rho={rho:.4f}, p-val={rho_p:.4e}")

        # H22: Binomial test for Book Asymmetry match rate > 50%
        book_matches = df_res["match_book"].sum()
        binom_book = stats.binomtest(book_matches, n_obs, p=0.5, alternative="greater")
        print(f"[H22 Binomial Test] Book Asymmetry Match Rate: {book_matches}/{n_obs} ({book_matches/n_obs*100:.1f}%), p-val={binom_book.pvalue:.4e}")

    print(f"[DONE] Saved C3 Directional Validation results to {out_csv}")
    return df_res
