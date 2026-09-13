"""Order Book Resilience & Post-Shock Recovery Time (Stage 5 B7, H30)."""

import glob
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR
from utils.paths import session_to_iso

# A spread counts as shocked above this multiple of the session's baseline, and as recovered
# once it falls back below the lower one. The gap between them is deliberate: a single
# threshold makes an episode hovering at the boundary flicker in and out of shock.
SHOCK_MULTIPLE = 2.0
RECOVERY_MULTIPLE = 1.5

# Below this many snapshots a median baseline is not identified and the recovery count is
# dominated by the window edge.
MIN_SNAPSHOTS = 20


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
            spreads = grp.sort_values("snapshot_time")["spread_bps"].to_numpy(dtype=np.float64)
            if len(spreads) < MIN_SNAPSHOTS:
                continue

            # Median, not mean. The baseline is meant to be the normal spread the book
            # returns to, and a mean over the same series the shocks are drawn from is
            # pulled up by them - most on the widest days, which is where resilience is
            # being measured. A few wide seconds barely move the median.
            baseline = float(np.median(spreads))
            if baseline <= 0:
                continue

            elevated = spreads > baseline * SHOCK_MULTIPLE
            recovered_level = baseline * RECOVERY_MULTIPLE

            # Consecutive elevated seconds are one episode. Counting each of them
            # separately inflated the shock count by the length of every episode and
            # biased the mean recovery time down: a ten-second widening was recorded as
            # ten shocks recovering in 10, 9, 8 ... 1 seconds.
            starts = np.flatnonzero(elevated & ~np.r_[False, elevated[:-1]])

            recovery_times = []
            unrecovered = 0
            for start in starts:
                below = np.flatnonzero(spreads[start:] <= recovered_level)
                if below.size:
                    recovery_times.append(int(below[0]))
                else:
                    # The spread never came back inside the window. Counted, not silently
                    # dropped - a session where nothing recovers is the most resilient
                    # looking one if only completed recoveries are averaged.
                    unrecovered += 1

            metrics.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "baseline_spread_bps": baseline,
                "n_snapshots": len(spreads),
                "n_shocks": int(starts.size),
                "n_unrecovered": unrecovered,
                "shock_seconds": int(elevated.sum()),
                "mean_recovery_time_sec": float(np.mean(recovery_times)) if recovery_times else np.nan,
                "median_recovery_time_sec": float(np.median(recovery_times)) if recovery_times else np.nan,
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
