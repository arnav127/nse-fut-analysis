"""Iceberg order detection and hidden liquidity contribution (Stage 3 A6, H19)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, LIQUID_SYMBOLS, RESULTS_DIR


def run_a6_iceberg_detection() -> pd.DataFrame:
    orders_path = str(Path(ENRICHED_DATA_DIR) / "cash_orders").replace("\\", "/")
    if not glob.glob(f"{orders_path}/*/*.parquet"):
        print("[WARN] Enriched orders missing for A6 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A6] Detecting Iceberg Orders & Hidden Volume...")
    liq_list = ", ".join(f"'{s}'" for s in LIQUID_SYMBOLS)

    query = f"""
    WITH base AS (
        SELECT 
            symbol, trade_date, is_expiry,
            CASE WHEN symbol IN ({liq_list}) THEN 'Liquid' ELSE 'Illiquid' END AS liquidity_group,
            participant_type,
            (volume_disclosed > 0 AND volume_disclosed < volume_original) AS is_iceberg,
            CASE 
                WHEN (volume_disclosed > 0 AND volume_disclosed < volume_original) 
                THEN (volume_original - volume_disclosed) 
                ELSE 0 
            END AS hidden_vol,
            volume_original
        FROM read_parquet('{orders_path}/*/*.parquet')
        WHERE is_settlement_window = True AND activity_type = 1
    )
    SELECT 
        symbol, trade_date, is_expiry, liquidity_group, participant_type,
        COUNT(*) AS total_orders,
        SUM(CASE WHEN is_iceberg THEN 1 ELSE 0 END) AS iceberg_orders,
        SUM(volume_original) AS total_volume,
        SUM(hidden_vol) AS total_hidden_volume,
        SUM(CASE WHEN is_iceberg THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS iceberg_ratio,
        SUM(hidden_vol) * 1.0 / (SUM(volume_original) + 1e-5) AS hidden_volume_ratio
    FROM base
    GROUP BY symbol, trade_date, is_expiry, liquidity_group, participant_type
    ORDER BY symbol, trade_date, participant_type
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a6_iceberg_detection.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A6 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A6 Iceberg Detection failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a6_iceberg_detection()
