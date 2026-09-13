"""Participant profiling (Custodian, Proprietary, NCNP) (Stage 3 A3, H13-H14)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR


def run_a3_participant_profile() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    if not glob.glob(f"{cash_path}/**/*.parquet", recursive=True):
        print("[WARN] Enriched trades missing for A3 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A3] Profiling Participant Segment Activity...")

    # One scan, not two.
    #
    # Every trade names both counterparties, so the buy and sell profiles are two
    # projections of the same row. Aggregating them as separate CTEs over the same
    # `read_parquet` meant reading and decoding the whole trade layer twice; unnesting a
    # two-element list per row produces the same output from a single pass.
    query = f"""
    WITH tape AS (
        SELECT
            symbol, trade_date, is_expiry, is_settlement_window, trade_quantity,
            trade_price,
            [ {{'side': 'BUY',  'participant_type': buy_participant_type}},
              {{'side': 'SELL', 'participant_type': sell_participant_type}} ] AS sides
        FROM read_parquet('{cash_path}/**/*.parquet')
        WHERE is_regular_market
    ),
    sided AS (
        SELECT
            symbol, trade_date, is_expiry, is_settlement_window, trade_quantity, trade_price,
            UNNEST(sides) AS s
        FROM tape
    )
    SELECT
        symbol, trade_date, is_expiry, is_settlement_window,
        s.participant_type AS participant_type,
        s.side AS side,
        SUM(trade_quantity) AS volume,
        SUM(trade_price * trade_quantity) AS value_inr,
        COUNT(*) AS trades
    FROM sided
    GROUP BY symbol, trade_date, is_expiry, is_settlement_window, s.participant_type, s.side
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
