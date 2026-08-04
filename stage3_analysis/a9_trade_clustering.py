"""Trade clustering and Herfindahl-Hirschman Index (HHI) concentration (Stage 3 A9, H25)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a9_trade_clustering() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched trades missing for A9 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A9] Analyzing Trade Concentration (HHI) & Clustering...")

    query = f"""
    WITH bucket_vol AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, time_bucket, is_expiry,
            SUM(trade_quantity) AS bucket_volume
        FROM read_parquet('{cash_path}/**/*.parquet')
        WHERE is_settlement_window = True
        GROUP BY TRIM(symbol), trade_date, time_bucket, is_expiry
    ),
    day_vol AS (
        SELECT 
            symbol, trade_date,
            SUM(bucket_volume) AS total_settlement_volume
        FROM bucket_vol
        GROUP BY symbol, trade_date
    )
    SELECT 
        b.symbol, b.trade_date, b.is_expiry,
        SUM(POWER((b.bucket_volume * 1.0 / d.total_settlement_volume), 2)) AS hhi_concentration,
        MAX(b.bucket_volume) * 1.0 / d.total_settlement_volume AS max_bucket_share
    FROM bucket_vol b
    JOIN day_vol d ON b.symbol = d.symbol AND b.trade_date = d.trade_date
    GROUP BY b.symbol, b.trade_date, b.is_expiry
    ORDER BY b.symbol, b.trade_date
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
