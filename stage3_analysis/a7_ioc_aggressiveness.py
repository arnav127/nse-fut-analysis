"""
a7_ioc_aggressiveness.py — IOC and Market order execution aggressiveness (H10, H11).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a7_ioc_aggressiveness(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for A7 analysis.")
        return

    print("[ANALYSIS A7] Analyzing IOC Aggressiveness & Market Orders...")
    df = spark.read.parquet(orders_path).filter(
        (F.col("is_settlement_window") == True) & (F.col("activity_type") == 1)
    )

    # Sub-window classification: Early (15:00-15:24) vs Late (15:25-15:30)
    df = df.withColumn("minute_num", F.minute(F.col("txn_datetime")))
    df = df.withColumn("sub_window", F.when(F.col("minute_num") >= 25, "Late").otherwise("Early"))

    grouped = df.groupBy("symbol", "trade_date", "time_bucket", "sub_window", "is_expiry").agg(
        F.count("*").alias("total_orders"),
        F.sum(F.when(F.col("ioc_flag") == "Y", 1).otherwise(0)).alias("ioc_orders"),
        F.sum(F.when(F.col("mkt_order_flag") == "Y", 1).otherwise(0)).alias("market_orders")
    ).withColumn("ioc_ratio", F.col("ioc_orders") / F.col("total_orders"))\
     .withColumn("mkt_ratio", F.col("market_orders") / F.col("total_orders"))\
     .withColumn("aggressive_ratio", (F.col("ioc_orders") + F.col("market_orders")) / F.col("total_orders"))

    res_pd = grouped.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "a7_ioc_aggressiveness.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A7 results to {out_csv}")
    return res_pd
