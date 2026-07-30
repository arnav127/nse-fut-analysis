"""
a9_trade_clustering.py — Trade Size Distribution & Concentration (H25).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a9_trade_clustering(spark=None):
    if spark is None:
        spark = get_spark()

    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    out_csv = os.path.join(RESULTS_DIR, "a9_trade_clustering.csv")

    if not os.path.exists(cash_path):
        print("[WARN] Enriched trades missing for A9 analysis.")
        return

    print("[ANALYSIS A9] Analyzing Trade Size Concentration & Clustering (H25)...")
    df = spark.read.parquet(cash_path).filter(F.col("is_settlement_window") == True)

    # Compute Herfindahl-Hirschman Index (HHI) for trade sizes per (symbol, date)
    grouped = df.groupBy("symbol", "trade_date", "is_expiry").agg(
        F.sum("trade_quantity").alias("tot_vol"),
        F.count("*").alias("trade_cnt"),
        F.max("trade_quantity").alias("max_trade_qty"),
        F.avg("trade_quantity").alias("avg_trade_qty"),
        F.sum(F.col("trade_quantity") * F.col("trade_quantity")).alias("sum_sq_qty")
    ).withColumn("hhi_concentration", F.col("sum_sq_qty") / (F.col("tot_vol") * F.col("tot_vol") + 1e-5))\
     .withColumn("max_to_avg_ratio", F.col("max_trade_qty") / (F.col("avg_trade_qty") + 1e-5))

    res_pd = grouped.toPandas()
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A9 results to {out_csv}")
    return res_pd
