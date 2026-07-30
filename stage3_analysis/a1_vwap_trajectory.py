"""
a1_vwap_trajectory.py — Reconstruct 1-minute cumulative & instantaneous VWAP and basis trajectory.
"""
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a1_vwap_trajectory(spark=None):
    if spark is None:
        spark = get_spark()

    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    fao_path = os.path.join(ENRICHED_DATA_DIR, "fao_trades")

    if not os.path.exists(cash_path) or not os.path.exists(fao_path):
        print("[WARN] Enriched trades missing for A1 analysis.")
        return

    print("[ANALYSIS A1] Computing VWAP Trajectory & Basis...")

    # Load cash trades in settlement window
    cash_df = spark.read.parquet(cash_path).filter(F.col("is_settlement_window") == True)
    # Load futures trades in settlement window
    fao_df = spark.read.parquet(fao_path).filter(F.col("is_settlement_window") == True)

    # 1. CASH minute-level aggregations
    cash_min = cash_df.groupBy("symbol", "trade_date", "time_bucket", "is_expiry", "liquidity_group").agg(
        F.sum(F.col("trade_price") * F.col("trade_quantity")).alias("cash_value"),
        F.sum("trade_quantity").alias("cash_volume"),
        F.count("*").alias("cash_trades")
    ).withColumn("cash_inst_vwap", F.col("cash_value") / F.col("cash_volume"))

    # Cumulative VWAP window partition by (symbol, trade_date) ordered by time_bucket
    cum_window = Window.partitionBy("symbol", "trade_date").orderBy("time_bucket").rowsBetween(Window.unboundedPreceding, Window.currentRow)

    cash_min = cash_min.withColumn("cum_cash_value", F.sum("cash_value").over(cum_window))\
                       .withColumn("cum_cash_volume", F.sum("cash_volume").over(cum_window))\
                       .withColumn("cash_cum_vwap", F.col("cum_cash_value") / F.col("cum_cash_volume"))

    # 2. FAO minute-level aggregations
    fao_min = fao_df.groupBy("symbol", "trade_date", "time_bucket").agg(
        F.sum(F.col("trade_price") * F.col("trade_quantity")).alias("fao_value"),
        F.sum("trade_quantity").alias("fao_volume"),
        F.count("*").alias("fao_trades")
    ).withColumn("futures_avg_price", F.col("fao_value") / F.col("fao_volume"))

    # 3. Join CASH and FAO
    result_df = cash_min.join(fao_min, on=["symbol", "trade_date", "time_bucket"], how="inner")\
                        .withColumn("basis_bps", ((F.col("futures_avg_price") - F.col("cash_cum_vwap")) / F.col("cash_cum_vwap")) * 10000.0)

    # Save to CSV
    out_csv = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    result_pd = result_df.toPandas()
    result_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A1 results ({len(result_pd)} rows) to {out_csv}")
    return result_pd
