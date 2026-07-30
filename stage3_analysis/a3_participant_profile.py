"""
a3_participant_profile.py — Participant profiling (Custodian, Proprietary, NCNP) (H3, H4).
"""
import os
from pyspark.sql import functions as F
from config.settings import ENRICHED_DATA_DIR, RESULTS_DIR
from utils.spark_session import get_spark

def run_a3_participant_profile(spark=None):
    if spark is None:
        spark = get_spark()

    cash_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    if not os.path.exists(cash_path):
        print("[WARN] Enriched trades missing for A3 analysis.")
        return

    print("[ANALYSIS A3] Profiling Participant Segment Activity...")
    df = spark.read.parquet(cash_path)

    # Buy side participant volume
    buy_df = df.groupBy("symbol", "trade_date", "is_expiry", "is_settlement_window", "buy_participant_type")\
               .agg(F.sum("trade_quantity").alias("volume"), F.count("*").alias("trades"))\
               .withColumnRenamed("buy_participant_type", "participant_type")\
               .withColumn("side", F.lit("BUY"))

    # Sell side participant volume
    sell_df = df.groupBy("symbol", "trade_date", "is_expiry", "is_settlement_window", "sell_participant_type")\
                .agg(F.sum("trade_quantity").alias("volume"), F.count("*").alias("trades"))\
                .withColumnRenamed("sell_participant_type", "participant_type")\
                .withColumn("side", F.lit("SELL"))

    combined = buy_df.union(sell_df)

    res_pd = combined.toPandas()
    out_csv = os.path.join(RESULTS_DIR, "a3_participant_profile.csv")
    res_pd.to_csv(out_csv, index=False)
    print(f"[DONE] Saved A3 results to {out_csv}")
    return res_pd
