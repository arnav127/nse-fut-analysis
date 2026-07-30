"""
a8_volatility_regime.py — Intraday Volatility Regime & Settlement RV Ratio (H24).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a8_volatility_regime(spark=None):
    if spark is None:
        spark = get_spark()

    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    out_csv = os.path.join(RESULTS_DIR, "a8_volatility_regime.csv")

    if not os.path.exists(cash_path):
        print("[WARN] Enriched trades missing for A8 analysis.")
        return

    print("[ANALYSIS A8] Analyzing Intraday Volatility Regimes (H24)...")
    df = spark.read.parquet(cash_path)

    # 5-minute realized volatility calculation
    # bucket_5m = 09:15-09:20, ..., 15:25-15:30
    df = df.withColumn("minute_val", F.minute(F.col("txn_datetime")))
    df = df.withColumn("hour_val", F.hour(F.col("txn_datetime")))
    df = df.withColumn("bucket_5m", F.concat(
        F.lpad(F.col("hour_val"), 2, "0"), F.lit(":"),
        F.lpad((F.col("minute_val") / 5).cast("int") * 5, 2, "0")
    ))

    grouped = df.groupBy("symbol", "trade_date", "is_expiry", "is_settlement_window", "bucket_5m").agg(
        F.stddev("trade_price").alias("price_std"),
        F.max("trade_price").alias("high_price"),
        F.min("trade_price").alias("low_price"),
        F.count("*").alias("trade_count")
    ).withColumn("garman_klass_vol", F.log(F.col("high_price") / F.col("low_price")))

    # Summary by day & settlement status
    summary = grouped.groupBy("symbol", "trade_date", "is_expiry").agg(
        F.mean(F.when(F.col("is_settlement_window") == True, F.col("price_std"))).alias("settlement_rv"),
        F.mean(F.when(F.col("is_settlement_window") == False, F.col("price_std"))).alias("pre_settlement_rv")
    ).withColumn("rv_ratio", F.col("settlement_rv") / (F.col("pre_settlement_rv") + 1e-5))

    res_pd = summary.toPandas()
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A8 results to {out_csv}")
    return res_pd
