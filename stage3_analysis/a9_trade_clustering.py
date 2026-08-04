"""Trade size distribution and concentration metrics (Stage 3 A9, H25)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a9_trade_clustering() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/*/*.parquet"):
        print("[WARN] Enriched trades missing for A9 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A9] Analyzing Trade Size Concentration & Clustering (H25)...")

    query = f"""
    SELECT 
        symbol, trade_date, is_expiry,
        SUM(trade_quantity) AS tot_vol,
        COUNT(*) AS trade_cnt,
        MAX(trade_quantity) AS max_trade_qty,
        AVG(trade_quantity) AS avg_trade_qty,
        SUM(trade_quantity * trade_quantity) AS sum_sq_qty,
        SUM(trade_quantity * trade_quantity) * 1.0 / (SUM(trade_quantity) * SUM(trade_quantity) + 1e-5) AS hhi_concentration,
        MAX(trade_quantity) * 1.0 / (AVG(trade_quantity) + 1e-5) AS max_to_avg_ratio
    FROM read_parquet('{cash_path}/*/*.parquet')
    WHERE is_settlement_window = True
    GROUP BY symbol, trade_date, is_expiry
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a9_trade_clustering.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A9 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A9 Trade Clustering failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a9_trade_clustering()
