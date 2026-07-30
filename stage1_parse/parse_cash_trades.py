"""
parse_cash_trades.py — Parse CASH_Trades_DDMMYYYY.DAT.gz files into Parquet.
"""
import os
from pyspark.sql import functions as F
from config.settings import (
    RAW_DATA_DIR, PARSED_DATA_DIR, TARGET_SYMBOLS_RAW, CASH_SERIES_FILTER
)
from config.schema_definitions import CM_TRADES_SCHEMA
from utils.spark_session import get_spark

def parse_cash_trades(date_str, spark=None):
    """
    Parse Cash Trades for a given DDMMYYYY date string.
    """
    out_dir = os.path.join(PARSED_DATA_DIR, "cash_trades", f"date={date_str}")
    if os.path.exists(out_dir) and len(os.listdir(out_dir)) > 0:
        print(f"[SKIP] CASH Trades for date={date_str} already parsed.")
        return

    in_file = os.path.join(RAW_DATA_DIR, f"CASH_Trades_{date_str}.DAT.gz")
    if not os.path.exists(in_file):
        print(f"[WARN] File not found: {in_file}")
        return

    print(f"[PARSE] CASH Trades for date={date_str}...")
    if spark is None:
        spark = get_spark()

    df_raw = spark.read.text(in_file)

    select_exprs = []
    for field_name, start, length, dtype in CM_TRADES_SCHEMA:
        col_expr = F.substring(F.col("value"), start + 1, length)
        if dtype in ("int", "long"):
            col_expr = col_expr.cast(dtype)
        select_exprs.append(col_expr.alias(field_name))

    df_parsed = df_raw.select(*select_exprs)

    df_filtered = df_parsed.filter(
        (F.col("symbol").isin(TARGET_SYMBOLS_RAW)) &
        (F.trim(F.col("series")) == CASH_SERIES_FILTER)
    ).withColumn("symbol", F.trim(F.col("symbol")))

    df_filtered.write.mode("overwrite").parquet(out_dir)
    print(f"[DONE] Saved parsed CASH Trades to {out_dir}")
