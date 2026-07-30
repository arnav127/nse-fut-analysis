"""
a11_amihud_illiquidity.py — Amihud Illiquidity Ratio Analysis (H27).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a11_amihud_illiquidity(spark=None):
    if spark is None:
        spark = get_spark()

    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    out_csv = os.path.join(RESULTS_DIR, "a11_amihud_illiquidity.csv")

    if not os.path.exists(cash_path):
        print("[WARN] Enriched trades missing for A11 analysis.")
        return

    print("[ANALYSIS A11] Calculating Amihud Illiquidity Ratio (H27)...")
    df = spark.read.parquet(cash_path)

    # 1-minute Amihud ratio = |return| / traded_value
    min_df = df.groupBy("symbol", "trade_date", "time_bucket", "is_expiry", "is_settlement_window").agg(
        F.first("trade_price").alias("first_price"),
        F.last("trade_price").alias("last_price"),
        F.sum(F.col("trade_price") * F.col("trade_quantity")).alias("traded_value")
    ).withColumn("abs_return", F.abs((F.col("last_price") - F.col("first_price")) / (F.col("first_price") + 1e-5)))\
     .withColumn("amihud_ratio", F.col("abs_return") / (F.col("traded_value") + 1.0))

    summary = min_df.groupBy("symbol", "trade_date", "is_expiry").agg(
        F.mean(F.when(F.col("is_settlement_window") == True, F.col("amihud_ratio"))).alias("amihud_settlement"),
        F.mean(F.when(F.col("is_settlement_window") == False, F.col("amihud_ratio"))).alias("amihud_pre_settlement")
    ).withColumn("amihud_uplift", F.col("amihud_settlement") / (F.col("amihud_pre_settlement") + 1e-12))

    res_pd = summary.toPandas()
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A11 Amihud Illiquidity results to {out_csv}")
    return res_pd
