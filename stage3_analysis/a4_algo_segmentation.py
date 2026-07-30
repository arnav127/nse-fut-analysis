"""
a4_algo_segmentation.py — Algo vs Non-Algo order flow analysis (H5, H6).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a4_algo_segmentation(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for A4 analysis.")
        return

    print("[ANALYSIS A4] Analyzing Algo vs Non-Algo Segmentation...")
    df = spark.read.parquet(orders_path).filter(F.col("activity_type") == 1) # Entry orders

    grouped = df.groupBy("symbol", "trade_date", "is_expiry", "is_settlement_window", "algo_type").agg(
        F.count("*").alias("total_orders"),
        F.sum("volume_original").alias("total_volume"),
        F.sum(F.when(F.col("ioc_flag") == "Y", 1).otherwise(0)).alias("ioc_orders"),
        F.sum(F.when(F.col("mkt_order_flag") == "Y", 1).otherwise(0)).alias("market_orders")
    ).withColumn("ioc_rate", F.col("ioc_orders") / F.col("total_orders"))\
     .withColumn("mkt_rate", F.col("market_orders") / F.col("total_orders"))

    res_pd = grouped.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "a4_algo_segmentation.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A4 results to {out_csv}")
    return res_pd
