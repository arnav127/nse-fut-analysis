"""Long/Short roll pressure calculation from Bloomberg spread & OI data (Stage 6 C1, H20-H21)."""

from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR, TARGET_SYMBOLS
from stage6_bloomberg.load_bloomberg_data import build_bloomberg_master


def run_c1_roll_pressure() -> pd.DataFrame:
    print("[ANALYSIS C1] Calculating Bloomberg Roll Pressure Direction...")
    df_bbg = build_bloomberg_master()
    out_csv = Path(RESULTS_DIR) / "c1_roll_pressure.csv"

    results = []
    expiry_dates = [pd.to_datetime(d, format="%d%m%Y") for d in EXPIRY_THURSDAYS_DDMMYYYY]

    for symbol in TARGET_SYMBOLS:
        for exp_dt in expiry_dates:
            exp_str = exp_dt.strftime("%Y-%m-%d")

            if df_bbg.empty or "calendar_spread" not in df_bbg.columns:
                results.append({
                    "symbol": symbol,
                    "expiry_date": exp_str,
                    "roll_direction_score": np.nan,
                    "predicted_punch_direction": "UNKNOWN",
                    "roll_intensity": np.nan,
                })
                continue

            sub = df_bbg[(df_bbg["symbol"] == symbol) & (df_bbg["date"] <= exp_dt)]
            sub = sub.sort_values("date").tail(5)

            if len(sub) < 2:
                score = 0.0
                pred_dir = "NEUTRAL"
            else:
                spread_start = sub["calendar_spread"].iloc[0]
                spread_end = sub["calendar_spread"].iloc[-1]
                sig1 = -1.0 if (spread_end < spread_start) else 1.0

                if "near_month_oi" in sub.columns and "far_month_oi" in sub.columns:
                    near_oi_change = sub["near_month_oi"].iloc[-1] - sub["near_month_oi"].iloc[0]
                    far_oi_change = sub["far_month_oi"].iloc[-1] - sub["far_month_oi"].iloc[0]
                    sig2 = -1.0 if (near_oi_change < 0 and far_oi_change > 0) else 1.0
                else:
                    sig2 = sig1

                if "actual_basis" in sub.columns:
                    basis_change = sub["actual_basis"].iloc[-1] - sub["actual_basis"].iloc[0]
                    sig3 = -1.0 if (basis_change < 0) else 1.0
                else:
                    sig3 = sig1

                vol_intensity = min(1.5, sub["volume_ratio"].iloc[-1]) if "volume_ratio" in sub.columns else 1.0

                composite_score = ((0.4 * sig1) + (0.3 * sig2) + (0.3 * sig3)) * vol_intensity
                score = float(np.clip(composite_score, -1.0, 1.0))
                pred_dir = "DOWN" if score < 0 else "UP"

            results.append({
                "symbol": symbol,
                "expiry_date": exp_str,
                "roll_direction_score": score,
                "predicted_punch_direction": pred_dir,
                "roll_intensity": abs(score),
            })

    df_res = pd.DataFrame(results)
    df_res.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C1 Roll Pressure results to {out_csv}")
    return df_res


if __name__ == "__main__":
    run_c1_roll_pressure()
