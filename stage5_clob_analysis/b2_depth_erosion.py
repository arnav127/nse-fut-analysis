"""Order book depth erosion and imbalance dynamics (Stage 5 B2, H5-H6)."""

import glob
from pathlib import Path

import duckdb
import pandas as pd

from config.settings import CLOB_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY, LIQUID_SYMBOLS, RESULTS_DIR
from utils.paths import session_to_iso


def run_b2_depth_erosion() -> pd.DataFrame:
    # Addresses the snapshot partitions explicitly rather than globbing the whole tree.
    # A recursive glob would also pick up any output left by an earlier layout and union
    # two different schemas into the same query.
    pattern = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    files = glob.glob(pattern, recursive=True)
    if not files:
        print("[WARN] No CLOB snapshot files found for B2 analysis.")
        return pd.DataFrame()

    print(f"[ANALYSIS B2] Analyzing Order Book Depth Erosion ({len(files)} files)...")
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
            AVG(total_bid_volume) AS avg_bid_depth,
            AVG(total_ask_volume) AS avg_ask_depth,
            AVG(book_imbalance) AS avg_book_imbalance
        FROM read_parquet('{pattern}')
        GROUP BY TRIM(symbol), trade_date
    )
    SELECT 
        symbol,
        trade_date,
        (trade_date IN ({expiry_list})) AS is_expiry,
        CASE WHEN symbol IN ({liq_list}) THEN 'Liquid' ELSE 'Illiquid' END AS liquidity_group,
        avg_bid_depth,
        avg_ask_depth,
        avg_book_imbalance,
        ABS(avg_book_imbalance) AS abs_imbalance
    FROM snap_agg
    ORDER BY symbol, trade_date
    """

    try:
        with duckdb.connect() as conn:
            res_df = conn.execute(query).df()
        out_csv = Path(RESULTS_DIR) / "b2_depth_erosion.csv"
        res_df.to_csv(out_csv, index=False)
        print(f"[DONE-DUCKDB] Saved B2 results ({len(res_df)} rows) to {out_csv}")
        return res_df
    except Exception as exc:
        print(f"[ERROR-DUCKDB] B2 Depth Erosion failed: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    run_b2_depth_erosion()
