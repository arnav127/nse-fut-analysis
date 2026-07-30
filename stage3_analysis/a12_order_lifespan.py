"""
a12_order_lifespan.py — Order Lifespan & Phantom Order Detection (H28).
"""
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a12_order_lifespan(spark=None):
    if spark is None:
        spark = get_spark()

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    out_csv = os.path.join(RESULTS_DIR, "a12_order_lifespan.csv")

    if not os.path.exists(orders_path):
        print("[WARN] Enriched orders missing for A12 analysis.")
        return

    print("[ANALYSIS A12] Analyzing Order Lifespan & Phantom Orders (H28)...")
    df = spark.read.parquet(orders_path).filter(F.col("is_settlement_window") == True)

    # Track time between Entry (1) and Cancel (3) for each order_number
    window_spec = Window.partitionBy("order_number").orderBy("activity_type")

    df = df.withColumn("entry_jiffies", F.min(F.when(F.col("activity_type") == 1, F.col("txn_time_jiffies"))).over(window_spec))
    df = df.withColumn("cancel_jiffies", F.min(F.when(F.col("activity_type") == 3, F.col("txn_time_jiffies"))).over(window_spec))

    canceled = df.filter(F.col("activity_type") == 3).withColumn(
        "lifespan_seconds", (F.col("cancel_jiffies") - F.col("entry_jiffies")) / 65536.0
    )

    # Phantom order = cancelled within < 1.0 second
    canceled = canceled.withColumn("is_phantom", F.col("lifespan_seconds") < 1.0)

    summary = canceled.groupBy("symbol", "trade_date", "is_expiry", "participant_type").agg(
        F.count("*").alias("total_cancelled_orders"),
        F.sum(F.when(F.col("is_phantom") == True, 1).otherwise(0)).alias("phantom_orders"),
        F.avg("lifespan_seconds").alias("avg_lifespan_sec")
    ).withColumn("phantom_order_rate", F.col("phantom_orders") / (F.col("total_cancelled_orders") + 1e-5))

    res_pd = summary.toPandas()
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A12 Order Lifespan results to {out_csv}")
    return res_pd
