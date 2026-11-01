"""Turnover, trade count and price of every NSE equity over the order book sample's sessions.

Used to place the placebo group in the cross-section of the market (where it ranks, and
whether its members are large enough to be index constituents). Reads the parsed cash trades.
"""

import glob
from pathlib import Path

import duckdb

files = glob.glob(str(Path.home() / "sandbox/BlockCrosser/data/parsed/cash_trades/"
                      "date=*/symbol=*/*.parquet"))
con = duckdb.connect()
con.execute("SET threads=6")
frame = con.execute("""
    SELECT symbol, COUNT(DISTINCT CAST(txn_time AS DATE)) AS sessions,
           SUM(CAST(trade_price AS DOUBLE) / 100 * trade_quantity) / 1e7 AS turnover_cr,
           COUNT(*) AS trades, median(CAST(trade_price AS DOUBLE) / 100) AS price
    FROM read_parquet(?, hive_partitioning = true)
    WHERE record_indicator = 'RM' AND trade_quantity > 0
    GROUP BY symbol
""", [files]).df()
out = Path(__file__).resolve().parent.parent / "data/results/s15_cash_cross_section.csv"
frame.to_csv(out, index=False)
print(len(frame), "securities")
