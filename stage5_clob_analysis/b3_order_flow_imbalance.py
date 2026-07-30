"""
b3_order_flow_imbalance.py — Order Flow Imbalance (OFI) analysis (H16).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_b3_order_flow_imbalance(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for B3 analysis.")
        return

    print("[ANALYSIS B3] Computing Order Flow Imbalance (OFI)...")
    df = spark.read.parquet(orders_path).filter(
        (F.col("is_settlement_window") == True) & (F.col("activity_type") == 1)
    )

    grouped = df.groupBy("symbol", "trade_date", "time_bucket", "is_expiry").agg(
        F.sum(F.when(F.col("buy_sell") == "B", F.col("volume_original")).otherwise(0)).alias("buy_volume"),
        F.sum(F.when(F.col("buy_sell") == "S", F.col("volume_original")).otherwise(0)).alias("sell_volume")
    ).withColumn("cash_ofi", (F.col("buy_volume") - F.col("sell_volume")) / (F.col("buy_volume") + F.col("sell_volume") + 1e-5))

    res_pd = grouped.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "b3_order_flow_imbalance.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved B3 results to {out_csv}")
    return res_pd
