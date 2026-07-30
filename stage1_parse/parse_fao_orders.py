"""
parse_fao_orders.py — Parse FAO_Orders_DDMMYYYY_nn.DAT.gz files into Parquet.
"""
import os
import glob
from pyspark.sql import functions as F
from config.settings import (
    RAW_DATA_DIR, PARSED_DATA_DIR, TARGET_SYMBOLS_RAW
)
from config.schema_definitions import FAO_ORDERS_SCHEMA
from utils.spark_session import get_spark

def parse_fao_orders(date_str, spark=None):
    """
    Parse FAO Orders for a given DDMMYYYY date string.
    Handles split files: FAO_Orders_DDMMYYYY_nn.DAT.gz
    """
    out_dir = os.path.join(PARSED_DATA_DIR, "fao_orders", f"date={date_str}")
    if os.path.exists(out_dir) and len(os.listdir(out_dir)) > 0:
        print(f"[SKIP] FAO Orders for date={date_str} already parsed.")
        return

    pattern = os.path.join(RAW_DATA_DIR, f"FAO_Orders_{date_str}*.DAT.gz")
    matching_files = glob.glob(pattern)
    if not matching_files:
        print(f"[WARN] No files matching: {pattern}")
        return

    print(f"[PARSE] FAO Orders for date={date_str} ({len(matching_files)} split files)...")
    if spark is None:
        spark = get_spark()

    df_raw = spark.read.text(pattern)
    # High-Performance Predicate Pushdown on raw string
    df_raw_filtered = df_raw.filter(
        (F.substring(F.col("value"), 39, 10).isin(TARGET_SYMBOLS_RAW)) &
        (F.trim(F.substring(F.col("value"), 49, 6)) == "FUTSTK")
    )

    select_exprs = []
    for field_name, start, length, dtype in FAO_ORDERS_SCHEMA:
        col_expr = F.substring(F.col("value"), start + 1, length)
        if dtype in ("int", "long"):
            col_expr = col_expr.cast(dtype)
        select_exprs.append(col_expr.alias(field_name))

    df_filtered = df_raw_filtered.select(*select_exprs).withColumn("symbol", F.trim(F.col("symbol")))

    df_filtered.write.mode("overwrite").parquet(out_dir)
    print(f"[DONE] Saved parsed FAO Orders to {out_dir}")
