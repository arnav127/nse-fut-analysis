"""
a6_iceberg_detection.py — Iceberg order detection and hidden liquidity (H9).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a6_iceberg_detection(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for A6 analysis.")
        return

    print("[ANALYSIS A6] Detecting Iceberg Orders & Hidden Volume...")
    df = spark.read.parquet(orders_path).filter(
        (F.col("is_settlement_window") == True) & (F.col("activity_type") == 1)
    )

    df = df.withColumn("is_iceberg", (F.col("volume_disclosed") > 0) & (F.col("volume_disclosed") < F.col("volume_original")))
    df = df.withColumn("hidden_volume", F.when(F.col("is_iceberg"), F.col("volume_original") - F.col("volume_disclosed")).otherwise(0))

    grouped = df.groupBy("symbol", "trade_date", "is_expiry", "liquidity_group", "participant_type").agg(
        F.count("*").alias("total_orders"),
        F.sum(F.when(F.col("is_iceberg"), 1).otherwise(0)).alias("iceberg_orders"),
        F.sum("volume_original").alias("total_volume"),
        F.sum("hidden_volume").alias("total_hidden_volume")
    ).withColumn("iceberg_ratio", F.col("iceberg_orders") / F.col("total_orders"))\
     .withColumn("hidden_volume_ratio", F.col("total_hidden_volume") / F.col("total_volume"))

    res_pd = grouped.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "a6_iceberg_detection.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A6 results to {out_csv}")
    return res_pd
