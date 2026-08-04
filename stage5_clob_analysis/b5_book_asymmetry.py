"""Directional order book pressure & asymmetry (Stage 5 B5, H22)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, RESULTS_DIR


def run_b5_book_asymmetry() -> pd.DataFrame:
    pattern = str(Path(CLOB_DATA_DIR) / "**" / "*.parquet").replace("\\", "/")
    files = glob.glob(pattern, recursive=True)
    if not files:
        print("[WARN] No CLOB snapshot files found for B5 analysis.")
        return pd.DataFrame()

    print("[ANALYSIS B5] Analyzing Directional Book Pressure & Asymmetry...")
    expiry_list = ", ".join(f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    query = f"""
    WITH base AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date,
            LN((total_bid_volume + 1.0) / (total_ask_volume + 1.0)) AS log_pressure,
            book_imbalance,
            snapshot_time
        FROM read_parquet('{pattern}')
    ),
    means AS (
        SELECT symbol, trade_date, AVG(book_imbalance) AS mean_imbalance
        FROM base
        GROUP BY symbol, trade_date
    )
    SELECT 
        b.symbol,
        b.trade_date,
        (b.trade_date IN ({expiry_list})) AS is_expiry,
        AVG(b.log_pressure) AS mean_log_pressure,
        AVG(CASE WHEN SIGN(b.book_imbalance) = SIGN(m.mean_imbalance) THEN 1.0 ELSE 0.0 END) AS book_pressure_persistence,
        LAST(b.book_imbalance ORDER BY b.snapshot_time) AS final_imbalance
    FROM base b
    JOIN means m ON b.symbol = m.symbol AND b.trade_date = m.trade_date
    GROUP BY b.symbol, b.trade_date
    ORDER BY b.symbol, b.trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_df = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "b5_book_asymmetry.csv"
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B5 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B5 Book Asymmetry failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b5_book_asymmetry()
