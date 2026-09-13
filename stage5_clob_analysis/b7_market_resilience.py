"""Order Book Resilience & Post-Shock Recovery Time (Stage 5 B7, H30)."""

import glob
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR
from utils.paths import session_to_iso


def run_b7_market_resilience() -> pd.DataFrame:
    # Addresses the snapshot partitions explicitly rather than globbing the whole tree.
    # A recursive glob would also pick up any output left by an earlier layout and union
    # two different schemas into the same query.
    pattern = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    files = glob.glob(pattern, recursive=True)
    out_csv = Path(RESULTS_DIR) / "b7_market_resilience.csv"

    if not files:
        print("[WARN] No CLOB snapshot files found for B7 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS B7] Analyzing Market Resilience & Recovery Time (H30)...")
    # The snapshot layer stores `trade_date` as ISO, derived from the record timestamp.
    # The expiry calendar is written the way NSE names its files, so it is converted here;
    # comparing the two spellings directly matched nothing and reported every session as a
    # control day.
    expiry_list = ", ".join(f"'{session_to_iso(d)}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    query = f"""
    SELECT 
        TRIM(symbol) AS symbol,
        trade_date,
        (trade_date IN ({expiry_list})) AS is_expiry,
        snapshot_time,
        spread_bps
    FROM read_parquet('{pattern}')
    WHERE spread_bps IS NOT NULL
    ORDER BY symbol, trade_date, snapshot_time
    """

    try:
        with duckdb.connect() as conn:
            df_all = conn.execute(query).df()

        metrics = []
        for (symbol, trade_date, is_expiry), grp in df_all.groupby(["symbol", "trade_date", "is_expiry"]):
            spreads = grp["spread_bps"].values
            if len(spreads) < 20:
                continue

            baseline_spread = np.mean(spreads)
            shock_threshold = baseline_spread * 2.0
            shock_indices = np.where(spreads > shock_threshold)[0]
            recovery_times = []

            for idx in shock_indices:
                recovered = np.where(spreads[idx:] <= baseline_spread * 1.5)[0]
                if len(recovered) > 0:
                    recovery_times.append(recovered[0])

            avg_recovery = float(np.mean(recovery_times)) if recovery_times else 0.0
            metrics.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "n_shocks": len(shock_indices),
                "mean_recovery_time_sec": avg_recovery,
            })

        res_df = pd.DataFrame(metrics)
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B7 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B7 Market Resilience failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b7_market_resilience()
