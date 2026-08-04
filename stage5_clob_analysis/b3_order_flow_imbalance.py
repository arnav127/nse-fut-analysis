"""Order Flow Imbalance (OFI) trajectory analysis (Stage 5 B3, H8-H10)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_b3_order_flow_imbalance() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched orders missing for B3 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS B3] Computing Order Flow Imbalance (OFI)...")

    query = f"""
    WITH base AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, time_bucket, is_expiry,
            SUM(CASE WHEN buy_sell = 'B' THEN volume_original ELSE 0 END) AS buy_volume,
            SUM(CASE WHEN buy_sell = 'S' THEN volume_original ELSE 0 END) AS sell_volume
        FROM read_parquet('{orders_path}/**/*.parquet')
        WHERE is_settlement_window = True AND activity_type = 1
        GROUP BY TRIM(symbol), trade_date, time_bucket, is_expiry
    )
    SELECT 
        symbol, trade_date, time_bucket, is_expiry,
        buy_volume, sell_volume,
        (buy_volume - sell_volume) * 1.0 / (buy_volume + sell_volume + 1e-5) AS cash_ofi
    FROM base
    ORDER BY symbol, trade_date, time_bucket
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "b3_order_flow_imbalance.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B3 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B3 Order Flow Imbalance failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b3_order_flow_imbalance()
