"""Intraday Volatility Regime & Settlement Realized Volatility Ratio (Stage 3 A8, H24)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a8_volatility_regime() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/*/*.parquet"):
        print("[WARN] Enriched trades missing for A8 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A8] Analyzing Intraday Volatility Regimes (H24)...")

    query = f"""
    WITH b5m AS (
        SELECT 
            symbol, trade_date, is_expiry, is_settlement_window,
            printf('%02d:%02d', EXTRACT(HOUR FROM txn_datetime), (EXTRACT(MINUTE FROM txn_datetime) / 5) * 5) AS bucket_5m,
            STDDEV(trade_price) AS price_std,
            MAX(trade_price) AS high_price,
            MIN(trade_price) AS low_price,
            COUNT(*) AS trade_count
        FROM read_parquet('{cash_path}/*/*.parquet')
        GROUP BY symbol, trade_date, is_expiry, is_settlement_window, 
                 EXTRACT(HOUR FROM txn_datetime), (EXTRACT(MINUTE FROM txn_datetime) / 5) * 5
    )
    SELECT 
        symbol, trade_date, is_expiry,
        AVG(CASE WHEN is_settlement_window = True THEN price_std END) AS settlement_rv,
        AVG(CASE WHEN is_settlement_window = False THEN price_std END) AS pre_settlement_rv,
        AVG(CASE WHEN is_settlement_window = True THEN price_std END) / 
            (AVG(CASE WHEN is_settlement_window = False THEN price_std END) + 1e-5) AS rv_ratio
    FROM b5m
    GROUP BY symbol, trade_date, is_expiry
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a8_volatility_regime.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A8 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A8 Volatility Regime failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a8_volatility_regime()
