"""
parse_cash_orders.py — Parse CASH_Orders_DDMMYYYY.DAT.gz files into Parquet.
"""
import os
from pyspark.sql import functions as F
from config.settings import (
    RAW_DATA_DIR, PARSED_DATA_DIR, TARGET_SYMBOLS_RAW, CASH_SERIES_FILTER
)
from config.schema_definitions import CM_ORDERS_SCHEMA
from utils.spark_session import get_spark

def parse_cash_orders(date_str, spark=None):
    """
    Parse Cash Orders for a given DDMMYYYY date string.
    """
    out_dir = os.path.join(PARSED_DATA_DIR, "cash_orders", f"date={date_str}")
    if os.path.exists(out_dir) and len(os.listdir(out_dir)) > 0:
        print(f"[SKIP] CASH Orders for date={date_str} already parsed.")
        return

    in_file = os.path.join(RAW_DATA_DIR, f"CASH_Orders_{date_str}.DAT.gz")
    if not os.path.exists(in_file):
        print(f"[WARN] File not found: {in_file}")
        return

    print(f"[PARSE] CASH Orders for date={date_str}...")
    if spark is None:
        spark = get_spark()

    df_raw = spark.read.text(in_file)
    # High-Performance Predicate Pushdown on raw string (avoids extracting/casting 17 columns on 98% non-target rows)
    df_raw_filtered = df_raw.filter(
        (F.substring(F.col("value"), 39, 10).isin(TARGET_SYMBOLS_RAW)) &
        (F.trim(F.substring(F.col("value"), 49, 2)) == CASH_SERIES_FILTER)
    )

    select_exprs = []
    for field_name, start, length, dtype in CM_ORDERS_SCHEMA:
        col_expr = F.substring(F.col("value"), start + 1, length)
        if dtype in ("int", "long"):
            col_expr = col_expr.cast(dtype)
        select_exprs.append(col_expr.alias(field_name))

    df_filtered = df_raw_filtered.select(*select_exprs).withColumn("symbol", F.trim(F.col("symbol")))

    df_filtered.write.mode("overwrite").parquet(out_dir)
    print(f"[DONE] Saved parsed CASH Orders to {out_dir}")
