"""Futures to Cash Lead-Lag & Granger Causality Analysis (Stage 3 A10, H26)."""

from pathlib import Path
from typing import Optional

import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

from config.settings import RESULTS_DIR


def run_a10_lead_lag() -> Optional[pd.DataFrame]:
    in_csv = Path(RESULTS_DIR) / "a1_vwap_trajectory.csv"
    out_csv = Path(RESULTS_DIR) / "a10_lead_lag.csv"

    if not in_csv.exists():
        print("[WARN] A1 VWAP trajectory missing for A10 analysis.")
        return None

    print("[ANALYSIS A10] Computing Lead-Lag & Granger Causality (H26)...")
    df = pd.read_csv(in_csv)

    results = []
    grouped = df.groupby(["symbol", "trade_date", "is_expiry"])

    for (symbol, trade_date, is_expiry), group in grouped:
        group_sorted = group.sort_values("time_bucket")
        if len(group_sorted) < 15:
            continue

        cash_ret = group_sorted["cash_inst_vwap"].pct_change().dropna()
        fut_ret = group_sorted["futures_avg_price"].pct_change().dropna()

        combined = pd.DataFrame({"cash": cash_ret, "futures": fut_ret}).dropna()
        if len(combined) < 10:
            continue

        f_stat = 0.0
        p_val = 1.0
        try:
            gc_res = grangercausalitytests(combined[["cash", "futures"]], maxlag=2, verbose=False)
            f_stat = gc_res[1][0]["ssr_ftest"][0]
            p_val = gc_res[1][0]["ssr_ftest"][1]
        except Exception:
            pass

        xcorr_lag1 = combined["futures"].shift(1).corr(combined["cash"])

        results.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "granger_f_stat": f_stat,
            "granger_p_val": p_val,
            "xcorr_lag1": xcorr_lag1,
        })

    res_df = pd.DataFrame(results)
    res_df.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A10 Lead-Lag results to {out_csv}")
    return res_df


if __name__ == "__main__":
    run_a10_lead_lag()
