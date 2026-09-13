"""Bid-Ask spread dynamics and expansion across settlement windows (Stage 5 B1, H3-H4)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, LIQUID_SYMBOLS, RESULTS_DIR
from utils.paths import session_to_iso


def run_b1_spread_dynamics() -> pd.DataFrame:
    # Addresses the snapshot partitions explicitly rather than globbing the whole tree.
    # A recursive glob would also pick up any output left by an earlier layout and union
    # two different schemas into the same query.
    pattern = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    files = glob.glob(pattern, recursive=True)
    if not files:
        print("[WARN] No CLOB snapshot files found for B1 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B1] Analyzing Bid-Ask Spread Dynamics ({len(files)} files)...")
    liq_list = ", ".join(f"'{s}'" for s in LIQUID_SYMBOLS)
    # The snapshot layer stores `trade_date` as ISO, derived from the record timestamp.
    # The expiry calendar is written the way NSE names its files, so it is converted here;
    # comparing the two spellings directly matched nothing and reported every session as a
    # control day.
    expiry_list = ", ".join(f"'{session_to_iso(d)}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)

    query = f"""
    WITH snap_agg AS (
        SELECT 
            TRIM(symbol) AS symbol, trade_date,
            AVG(spread_bps) AS mean_spread_bps,
            MAX(spread_bps) AS max_spread_bps,
            MIN(spread_bps) AS min_spread_bps,
            STDDEV(spread_bps) AS std_spread_bps,
            FIRST(spread_bps ORDER BY snapshot_time) AS spread_at_1500,
            LAST(spread_bps ORDER BY snapshot_time) AS spread_at_1530
        FROM read_parquet('{pattern}')
        WHERE spread_bps IS NOT NULL
        GROUP BY TRIM(symbol), trade_date
    )
    SELECT 
        symbol,
        trade_date,
        (trade_date IN ({expiry_list})) AS is_expiry,
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

    try:
        with duckdb.connect() as conn:
            res_df = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "b1_spread_dynamics.csv"
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B1 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B1 Spread Dynamics failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b1_spread_dynamics()
