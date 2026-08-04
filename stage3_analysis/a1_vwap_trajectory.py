"""Reconstruct 1-minute VWAP trajectory and intraday basis dynamics (Stage 3 A1)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import ENRICHED_DATA_DIR, LIQUID_SYMBOLS, RESULTS_DIR


def run_a1_vwap_trajectory() -> pd.DataFrame:
    cash_path = str(Path(ENRICHED_DATA_DIR) / "cash_trades").replace("\\", "/")
    fao_path = str(Path(ENRICHED_DATA_DIR) / "fao_trades").replace("\\", "/")

    cash_files = glob.glob(f"{cash_path}/*/*.parquet")
    fao_files = glob.glob(f"{fao_path}/*/*.parquet")
    if not cash_files or not fao_files:
        print("[WARN] Enriched trades missing for A1 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS A1] Computing VWAP Trajectory & Basis...")
    liq_list = ", ".join(f"'{s}'" for s in LIQUID_SYMBOLS)

    query = f"""
    WITH cash_min AS (
        SELECT 
            symbol, trade_date, time_bucket, is_expiry,
            SUM(trade_price * trade_quantity) AS cash_value,
            SUM(trade_quantity) AS cash_volume,
            COUNT(*) AS cash_trades,
            SUM(trade_price * trade_quantity) / SUM(trade_quantity) AS cash_inst_vwap,
            SUM(SUM(trade_price * trade_quantity)) OVER (
                PARTITION BY symbol, trade_date 
                ORDER BY time_bucket 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cum_cash_value,
            SUM(SUM(trade_quantity)) OVER (
                PARTITION BY symbol, trade_date 
                ORDER BY time_bucket 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cum_cash_volume
        FROM read_parquet('{cash_path}/*/*.parquet')
        WHERE is_settlement_window = True
        GROUP BY symbol, trade_date, time_bucket, is_expiry
    ),
    fao_min AS (
        SELECT 
            symbol, trade_date, time_bucket,
            SUM(trade_price * trade_quantity) / SUM(trade_quantity) AS futures_avg_price
        FROM read_parquet('{fao_path}/*/*.parquet')
        WHERE is_settlement_window = True
        GROUP BY symbol, trade_date, time_bucket
    )
    SELECT 
        c.symbol,
        c.trade_date,
        c.time_bucket,
        c.is_expiry,
        c.cash_value,
        c.cash_volume,
        c.cash_trades,
        c.cash_inst_vwap,
        c.cum_cash_value,
        c.cum_cash_volume,
        c.cum_cash_value / c.cum_cash_volume AS cash_cum_vwap,
        f.futures_avg_price,
        ((f.futures_avg_price - (c.cum_cash_value / c.cum_cash_volume)) / (c.cum_cash_value / c.cum_cash_volume)) * 10000.0 AS basis_bps,
        CASE WHEN c.symbol IN ({liq_list}) THEN 'Liquid' ELSE 'Illiquid' END AS liquidity_group
    FROM cash_min c
    JOIN fao_min f ON c.symbol = f.symbol AND c.trade_date = f.trade_date AND c.time_bucket = f.time_bucket
    ORDER BY c.symbol, c.trade_date, c.time_bucket
    """

    try:
        with duckdb.connect() as conn:
            res_pd = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "a1_vwap_trajectory.csv"
        res_pd.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved A1 results ({len(res_pd)} rows) to {out_csv}")
        return res_pd
    except Exception as exc:
        print(f"[ERROR-DUCKDB] A1 VWAP Trajectory failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_a1_vwap_trajectory()
