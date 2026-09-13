"""Futures-to-cash lead-lag and Granger causality (Stage 3 A10, H26)."""

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

from config.settings import RESULTS_DIR

# Minute buckets needed before a Granger test on two lags is worth running. Two lags cost
# five parameters in the unrestricted model; below roughly three times that the F statistic
# is too noisy to interpret and the test is skipped rather than reported.
MIN_OBSERVATIONS = 15
MAX_LAG = 2


def run_a10_lead_lag() -> Optional[pd.DataFrame]:
    in_csv = Path(RESULTS_DIR) / "a1_vwap_trajectory.csv"
    out_csv = Path(RESULTS_DIR) / "a10_lead_lag.csv"

    if not in_csv.exists():
        print("[WARN] A1 VWAP trajectory missing for A10 analysis.")
        return None

    print("[ANALYSIS A10] Computing Lead-Lag & Granger Causality (H26)...")
    df = pd.read_csv(in_csv)

    if "futures_avg_price" not in df.columns or df["futures_avg_price"].notna().sum() == 0:
        # Without futures prices there is no lead-lag relationship to test. Writing an empty
        # file and saying so beats writing a file full of f=0, p=1 rows that read as a
        # tested-and-rejected result.
        print("[WARN] A1 output carries no futures prices (no FAO data parsed); "
              "H26 cannot be tested. Writing an empty A10 result.")
        empty = pd.DataFrame(columns=["symbol", "trade_date", "is_expiry", "n_obs",
                                      "granger_f_stat", "granger_p_val", "xcorr_lag1",
                                      "xcorr_lag0"])
        empty.to_csv(out_csv, index=False)
        return empty

    results = []
    skipped_short = 0
    failed = []

    for (symbol, trade_date, is_expiry), group in df.groupby(["symbol", "trade_date", "is_expiry"]):
        group = group.sort_values("time_bucket")
        # Returns are aligned on the minute bucket before anything is dropped. Taking
        # pct_change on each series separately and then dropping missing values
        # independently would leave two series of different lengths silently paired by
        # position wherever a minute had cash trades but no futures trades.
        paired = pd.DataFrame({
            "cash": group["cash_inst_vwap"].pct_change(),
            "futures": group["futures_avg_price"].pct_change(),
        }).replace([np.inf, -np.inf], np.nan).dropna()

        if len(paired) < MIN_OBSERVATIONS:
            skipped_short += 1
            continue
        # A constant series makes the regression singular and the correlation undefined.
        if paired["cash"].std() == 0 or paired["futures"].std() == 0:
            skipped_short += 1
            continue

        f_stat = p_val = np.nan
        try:
            # Column order matters: this tests whether the second series (futures) Granger
            # causes the first (cash), which is the direction H26 states.
            #
            # No `verbose` argument. It was deprecated in statsmodels 0.14 and removed in
            # 0.15; passing it used to be swallowed by a bare `except`, which turned every
            # row into f=0, p=1 - a null result indistinguishable from a real one.
            gc = grangercausalitytests(paired[["cash", "futures"]], maxlag=MAX_LAG)
            f_stat, p_val = gc[1][0]["ssr_ftest"][0], gc[1][0]["ssr_ftest"][1]
        except Exception as exc:
            failed.append(f"{symbol} {trade_date}: {type(exc).__name__}: {exc}")

        results.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "is_expiry": is_expiry,
            "n_obs": len(paired),
            "granger_f_stat": f_stat,
            "granger_p_val": p_val,
            # Lag 0 alongside lag 1: a futures lead shows as lag-1 correlation exceeding
            # contemporaneous correlation, and reporting only lag 1 leaves no way to see it.
            "xcorr_lag0": paired["futures"].corr(paired["cash"]),
            "xcorr_lag1": paired["futures"].shift(1).corr(paired["cash"]),
        })

    res_df = pd.DataFrame(results)
    res_df.to_csv(out_csv, index=False)

    if skipped_short:
        print(f"[A10] skipped {skipped_short} symbol-sessions with fewer than "
              f"{MIN_OBSERVATIONS} paired minutes")
    if failed:
        print(f"[A10] Granger test failed on {len(failed)} symbol-sessions; first: {failed[0]}")
    print(f"[DONE] Saved A10 results ({len(res_df)} rows) to {out_csv}")
    return res_df


if __name__ == "__main__":
    run_a10_lead_lag()
