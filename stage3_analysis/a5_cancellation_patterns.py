"""Order cancellation-to-entry ratio and fleeting liquidity patterns (Stage 3 A5, H17-H18)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a5_cancellation_patterns() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/*/*.parquet"):
        print("[WARN] Enriched orders missing for A5 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A5] Analyzing Cancellation Patterns...")

    query = f"""
    SELECT 
        symbol, trade_date, time_bucket, is_expiry, participant_type, algo_type,
        SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END) AS entries,
        SUM(CASE WHEN activity_type = 3 THEN 1 ELSE 0 END) AS cancellations,
        SUM(CASE WHEN activity_type = 4 THEN 1 ELSE 0 END) AS modifications,
        CASE 
            WHEN SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END) > 0 
            THEN SUM(CASE WHEN activity_type = 3 THEN 1 ELSE 0 END) * 1.0 / SUM(CASE WHEN activity_type = 1 THEN 1 ELSE 0 END)
            ELSE 0.0 
        END AS cancel_to_entry_ratio
    FROM read_parquet('{orders_path}/*/*.parquet')
    WHERE is_settlement_window = True
    GROUP BY symbol, trade_date, time_bucket, is_expiry, participant_type, algo_type
    ORDER BY symbol, trade_date, time_bucket
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a5_cancellation_patterns.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A5 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A5 Cancellation Patterns failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a5_cancellation_patterns()
