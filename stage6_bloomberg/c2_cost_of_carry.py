"""Fair value basis and implied repo mispricing analysis (Stage 6 C2, H23)."""

from pathlib import Path

import pandas as pd

from config.settings import RESULTS_DIR
from stage6_bloomberg.load_bloomberg_data import load_cost_of_carry


def run_c2_cost_of_carry() -> pd.DataFrame:
    print("[ANALYSIS C2] Analyzing Cost of Carry & Mispricing...")
    df_coc = load_cost_of_carry()
    out_csv = Path(RESULTS_DIR) / "c2_cost_of_carry.csv"

    if df_coc.empty:
        df_res = pd.DataFrame(columns=["symbol", "date", "actual_basis", "theoretical_basis", "mispricing_bps"])
        df_res.to_csv(out_csv, index=False)
        print(f"[DONE] Saved C2 results to {out_csv}")
        return df_res

    risk_free_rate = 0.06
    df_coc["theoretical_basis"] = df_coc["spot_close"] * risk_free_rate * (df_coc["days_to_expiry"] / 365.0)
    df_coc["mispricing_bps"] = ((df_coc["actual_basis"] - df_coc["theoretical_basis"]) / df_coc["spot_close"]) * 10000.0

    df_coc.to_csv(out_csv, index=False)
    print(f"[DONE] Saved C2 results to {out_csv}")
    return df_coc


if __name__ == "__main__":
    run_c2_cost_of_carry()
