"""
b1_spread_dynamics.py — Bid-Ask spread dynamics and expansion (H12, H13) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import CLOB_DATA_DIR, RESULTS_DIR, LIQUID_SYMBOLS, EXPIRY_THURSDAYS_DDMMYYYY

def run_b1_spread_dynamics():
    pattern = os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet").replace("\\", "/")
    files = glob.glob(pattern)
    if not files:
        print("[WARN] No CLOB snapshot files found for B1 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B1] Analyzing Bid-Ask Spread Dynamics ({len(files)} files via DuckDB C++)...")
    liq_list = ", ".join([f"'{s}'" for s in LIQUID_SYMBOLS])
    expiry_list = ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

    query = f"""
    WITH snap_agg AS (
        SELECT 
            symbol, trade_date,
            AVG(spread_bps) AS mean_spread_bps,
            MAX(spread_bps) AS max_spread_bps,
            MIN(spread_bps) AS min_spread_bps,
            STDDEV(spread_bps) AS std_spread_bps,
            FIRST(spread_bps ORDER BY snapshot_time) AS spread_at_1500,
            LAST(spread_bps ORDER BY snapshot_time) AS spread_at_1530
        FROM read_parquet('{pattern}')
        WHERE spread_bps IS NOT NULL
        GROUP BY symbol, trade_date
    )
    SELECT 
        symbol,
        trade_date,
        (strftime(CAST(trade_date AS DATE), '%d%m%Y') IN ({expiry_list})) AS is_expiry,
        CASE WHEN symbol IN ({liq_list}) THEN 'Liquid' ELSE 'Illiquid' END AS liquidity_group,
        mean_spread_bps,
        max_spread_bps,
        min_spread_bps,
        std_spread_bps,
        spread_at_1500,
        spread_at_1530
    FROM snap_agg
    ORDER BY symbol, trade_date
    """

    conn = duckdb.connect()
    try:
        res_df = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "b1_spread_dynamics.csv")
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B1 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as e:
        print(f"[ERROR-DUCKDB] B1 Spread Dynamics failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_b1_spread_dynamics()
