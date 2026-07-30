"""
a5_cancellation_patterns.py — Cancellation patterns and spoofing detection (H7, H8).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a5_cancellation_patterns(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for A5 analysis.")
        return

    print("[ANALYSIS A5] Analyzing Cancellation Patterns...")
    df = spark.read.parquet(orders_path).filter(F.col("is_settlement_window") == True)

    grouped = df.groupBy("symbol", "trade_date", "time_bucket", "is_expiry", "participant_type", "algo_type").agg(
        F.sum(F.when(F.col("activity_type") == 1, 1).otherwise(0)).alias("entries"),
        F.sum(F.when(F.col("activity_type") == 3, 1).otherwise(0)).alias("cancellations"),
        F.sum(F.when(F.col("activity_type") == 4, 1).otherwise(0)).alias("modifications")
    ).withColumn("cancel_to_entry_ratio", F.when(F.col("entries") > 0, F.col("cancellations") / F.col("entries")).otherwise(0.0))

    res_pd = grouped.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "a5_cancellation_patterns.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A5 results to {out_csv}")
    return res_pd
