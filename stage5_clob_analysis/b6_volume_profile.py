"""Settlement Volume Profile & Gini Concentration (Stage 5 B6, H29)."""

import glob
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR
from utils.paths import session_to_iso


def _gini_coefficient(x: np.ndarray) -> float:
    x_arr = np.asarray(x, dtype=np.float64)
    if np.amin(x_arr) < 0:
        x_arr -= np.amin(x_arr)
    x_arr += 1e-7
    x_sorted = np.sort(x_arr)
    n = x_sorted.size
    idx = np.arange(1, n + 1)
    return float(np.sum((2 * idx - n - 1) * x_sorted) / (n * np.sum(x_sorted)))


def run_b6_volume_profile() -> pd.DataFrame:
    # Addresses the snapshot partitions explicitly rather than globbing the whole tree.
    # A recursive glob would also pick up any output left by an earlier layout and union
    # two different schemas into the same query.
    pattern = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    files = glob.glob(pattern, recursive=True)
    out_csv = Path(RESULTS_DIR) / "b6_volume_profile.csv"

    if not files:
        print("[WARN] No CLOB snapshot files found for B6 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS B6] Analyzing Settlement Volume Profile & Gini Index (H29)...")
    # The snapshot layer stores `trade_date` as ISO, derived from the record timestamp.
    # The expiry calendar is written the way NSE names its files, so it is converted here;
    # comparing the two spellings directly matched nothing and reported every session as a
    # control day.
    expiry_list = ", ".join(f"'{session_to_iso(d)}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    # Traded volume, not resting depth.
    #
    # This measured `total_bid_volume + total_ask_volume`, which is the size sitting in the
    # book at each snapshot - a stock, not a flow. Its Gini described how unevenly *depth*
    # was distributed across the window, while H29 is about when trading actually happens.
    # The two can move in opposite directions: depth is thinnest in the minute that trades
    # most. `interval_volume_matched` is the quantity matched between consecutive snapshots,
    # which nsetick reports and the previous book could not produce at all.
    #
    # Aggregated to minutes, which is what "final minute share" has always claimed to
    # measure; per-second buckets made that the final second.
    query = f"""
    SELECT
        symbol,
        trade_date,
        trade_date IN ({expiry_list}) AS is_expiry,
        seconds_from_1500 // 60 AS minute_from_1500,
        SUM(interval_volume_matched) AS traded_volume,
        AVG(total_bid_volume + total_ask_volume) AS mean_book_depth
    FROM read_parquet('{pattern}')
    GROUP BY symbol, trade_date, is_expiry, minute_from_1500
    ORDER BY symbol, trade_date, minute_from_1500
    """

    try:
        with duckdb.connect() as conn:
            df_mins = conn.execute(query).df()

        metrics = []
        for (symbol, trade_date, is_expiry), grp in df_mins.groupby(["symbol", "trade_date", "is_expiry"]):
            grp = grp.sort_values("minute_from_1500")
            vol_vals = grp["traded_volume"].to_numpy(dtype=np.float64)
            depth_vals = grp["mean_book_depth"].to_numpy(dtype=np.float64)
            total = vol_vals.sum()
            if len(vol_vals) < 5 or total <= 0:
                continue
            metrics.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "n_minutes": len(vol_vals),
                "settlement_volume": float(total),
                "volume_gini": _gini_coefficient(vol_vals),
                "depth_gini": _gini_coefficient(depth_vals),
                # A minute with no trades makes a ratio against the minimum infinite, which
                # is exactly the case on a thin name. Reported against the median instead.
                "peak_to_median_ratio": float(np.max(vol_vals) / max(np.median(vol_vals), 1.0)),
                "final_min_share": float(vol_vals[-1] / total),
                "last_five_min_share": float(vol_vals[-5:].sum() / total),
            })

        res_df = pd.DataFrame(metrics)
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B6 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B6 Volume Profile failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b6_volume_profile()
