"""
a3_participant_profile.py — Participant profiling (Custodian, Proprietary, NCNP) (H3, H4) via DuckDB.
"""
import os
import glob
import duckdb
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR

def run_a3_participant_profile():
    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades").replace("\\", "/")
    files = glob.glob(f"{cash_path}/*/*.parquet")
    if not files:
        print("[WARN] Enriched trades missing for A3 analysis (DuckDB).")
        return pd.DataFrame()

    print("[ANALYSIS A3] Profiling Participant Segment Activity (DuckDB C++)...")

    query = f"""
    WITH buy_side AS (
        SELECT 
            symbol, trade_date, is_expiry, is_settlement_window,
            buy_participant_type AS participant_type,
            SUM(trade_quantity) AS volume,
            COUNT(*) AS trades,
            'BUY' AS side
        FROM read_parquet('{cash_path}/*/*.parquet')
        GROUP BY symbol, trade_date, is_expiry, is_settlement_window, buy_participant_type
    ),
    sell_side AS (
        SELECT 
            symbol, trade_date, is_expiry, is_settlement_window,
            sell_participant_type AS participant_type,
            SUM(trade_quantity) AS volume,
            COUNT(*) AS trades,
            'SELL' AS side
        FROM read_parquet('{cash_path}/*/*.parquet')
        GROUP BY symbol, trade_date, is_expiry, is_settlement_window, sell_participant_type
    )
    SELECT * FROM buy_side
    UNION ALL
    SELECT * FROM sell_side
    ORDER BY symbol, trade_date, side, participant_type
    """

    conn = duckdb.connect()
    try:
        res_pd = conn.execute(query).df()
        out_csv = os.path.join(RESULTS_DIR, "a3_participant_profile.csv")
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A3 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as e:
        print(f"[ERROR-DUCKDB] A3 Participant Profile failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

if __name__ == "__main__":
    run_a3_participant_profile()
