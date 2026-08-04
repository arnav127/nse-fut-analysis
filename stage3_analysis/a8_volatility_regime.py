"""Intraday volatility regime and settlement RV ratio calculation (Stage 3 A8, H24)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a8_volatility_regime() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched trades missing for A8 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A8] Calculating Volatility Regime & Settlement RV Ratio...")

    query = f"""
    WITH min_returns AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date, time_bucket, is_expiry, is_settlement_window,
            SUM(trade_price * trade_quantity) / SUM(trade_quantity) AS vwap_price,
            LN((SUM(trade_price * trade_quantity) / SUM(trade_quantity)) / 
               LAG(SUM(trade_price * trade_quantity) / SUM(trade_quantity)) 
               OVER (PARTITION BY TRIM(symbol), trade_date ORDER BY time_bucket)) AS log_return
        FROM read_parquet('{cash_path}/**/*.parquet')
        GROUP BY TRIM(symbol), trade_date, time_bucket, is_expiry, is_settlement_window
    ),
    rv_calc AS (
        SELECT 
            symbol, trade_date, is_expiry,
            SUM(CASE WHEN is_settlement_window = True THEN log_return * log_return ELSE 0 END) AS rv_settlement,
            SUM(CASE WHEN is_settlement_window = False THEN log_return * log_return ELSE 0 END) AS rv_presettlement
        FROM min_returns
        WHERE log_return IS NOT NULL
        GROUP BY symbol, trade_date, is_expiry
    )
    SELECT 
        symbol, trade_date, is_expiry,
        rv_settlement,
        rv_presettlement,
        rv_settlement / (rv_presettlement + 1e-8) AS rv_ratio
    FROM rv_calc
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
