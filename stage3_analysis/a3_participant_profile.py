"""Participant profiling (Custodian, Proprietary, NCNP) (Stage 3 A3, H13-H14)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a3_participant_profile() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/*/*.parquet"):
        print("[WARN] Enriched trades missing for A3 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A3] Profiling Participant Segment Activity...")

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

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a3_participant_profile.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A3 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A3 Participant Profile failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a3_participant_profile()
