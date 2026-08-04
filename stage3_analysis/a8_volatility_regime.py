"""
a8_volatility_regime.py — Intraday Volatility Regime & Settlement RV Ratio (H24) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a8_volatility_regime():
    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades").replace("\\", "/")
    files = glob.glob(f"{cash_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched trades missing for A8 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A8] Analyzing Intraday Volatility Regimes (H24) (DuckDB C++)...")

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

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a8_volatility_regime.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A8 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A8 Volatility Regime failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a8_volatility_regime()
