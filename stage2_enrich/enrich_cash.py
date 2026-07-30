"""
enrich_cash.py — Enrich parsed CASH orders and trades with timestamps, prices, and labels.
"""
import os
from pyspark.sql import functions as F
from config.settings import (
    PARSED_DATA_DIR, ENRICHED_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY,
    SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END, LIQUID_SYMBOLS
)
from utils.jiffies_converter import add_datetime_column
from utils.spark_session import get_spark

def _get_participant_mapping():
    return F.create_map([F.lit(1), F.lit("Custodian"), F.lit(2), F.lit("Proprietary"), F.lit(3), F.lit("NCNP")])

def _get_algo_mapping():
    return F.create_map([F.lit(0), F.lit("Algo"), F.lit(1), F.lit("Non-Algo"), F.lit(2), F.lit("Algo-SOR"), F.lit(3), F.lit("Non-Algo-SOR")])

def _get_activity_mapping():
    return F.create_map([F.lit(1), F.lit("Entry"), F.lit(3), F.lit("Cancel"), F.lit(4), F.lit("Modify")])

def enrich_cash_orders(spark=None):
    parsed_path = os.path.join(PARSED_DATA_DIR, "cash_orders")
    out_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    if not os.path.exists(parsed_path):
        print(f"[WARN] Parsed path does not exist: {parsed_path}")
        return

    if spark is None:
        spark = get_spark()

    print("[ENRICH] Enriching CASH Orders...")
    df = spark.read.parquet(parsed_path)

    # Extract date_str from path partition if present, or add column
    df = add_datetime_column(df, "txn_time_jiffies", "txn_datetime")
    df = df.withColumn("trade_date", F.date_format(F.col("txn_datetime"), "yyyy-MM-dd"))
    df = df.withColumn("trade_time", F.date_format(F.col("txn_datetime"), "HH:mm:ss"))
    df = df.withColumn("time_bucket", F.concat(F.date_format(F.col("txn_datetime"), "HH:mm"), F.lit(":00")))

    # Convert paise to rupees
    df = df.withColumn("limit_price", F.col("limit_price").cast("double") / 100.0)
    df = df.withColumn("trigger_price", F.col("trigger_price").cast("double") / 100.0)

    # Flags
    df = df.withColumn("is_settlement_window",
                       (F.col("trade_time") >= SETTLEMENT_WINDOW_START) &
                       (F.col("trade_time") <= SETTLEMENT_WINDOW_END))

    # Identify if date is in expiry thursdays
    date_clean = F.date_format(F.col("txn_datetime"), "ddMMyyyy")
    df = df.withColumn("is_expiry", date_clean.isin(EXPIRY_THURSDAYS_DDMMYYYY))

    # Mappings
    p_map = _get_participant_mapping()
    a_map = _get_algo_mapping()
    act_map = _get_activity_mapping()

    df = df.withColumn("participant_type", F.coalesce(p_map[F.col("client_identity")], F.lit("Unknown")))
    df = df.withColumn("algo_type", F.coalesce(a_map[F.col("algo_indicator")], F.lit("Unknown")))
    df = df.withColumn("activity_label", F.coalesce(act_map[F.col("activity_type")], F.lit("Unknown")))
    df = df.withColumn("liquidity_group", F.when(F.col("symbol").isin(LIQUID_SYMBOLS), "Liquid").otherwise("Illiquid"))

    df.write.mode("overwrite").partitionBy("trade_date").parquet(out_path)
    print(f"[DONE] Enriched CASH Orders saved to {out_path}")

def enrich_cash_trades(spark=None):
    parsed_path = os.path.join(PARSED_DATA_DIR, "cash_trades")
    out_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
    if not os.path.exists(parsed_path):
        print(f"[WARN] Parsed path does not exist: {parsed_path}")
        return

    if spark is None:
        spark = get_spark()

    print("[ENRICH] Enriching CASH Trades...")
    df = spark.read.parquet(parsed_path)

    df = add_datetime_column(df, "txn_time_jiffies", "txn_datetime")
    df = df.withColumn("trade_date", F.date_format(F.col("txn_datetime"), "yyyy-MM-dd"))
    df = df.withColumn("trade_time", F.date_format(F.col("txn_datetime"), "HH:mm:ss"))
    df = df.withColumn("time_bucket", F.concat(F.date_format(F.col("txn_datetime"), "HH:mm"), F.lit(":00")))

    # Convert trade price
    df = df.withColumn("trade_price", F.col("trade_price").cast("double") / 100.0)

    # Flags
    df = df.withColumn("is_settlement_window",
                       (F.col("trade_time") >= SETTLEMENT_WINDOW_START) &
                       (F.col("trade_time") <= SETTLEMENT_WINDOW_END))

    date_clean = F.date_format(F.col("txn_datetime"), "ddMMyyyy")
    df = df.withColumn("is_expiry", date_clean.isin(EXPIRY_THURSDAYS_DDMMYYYY))

    p_map = _get_participant_mapping()
    a_map = _get_algo_mapping()

    df = df.withColumn("buy_participant_type", F.coalesce(p_map[F.col("buy_client_identity")], F.lit("Unknown")))
    df = df.withColumn("sell_participant_type", F.coalesce(p_map[F.col("sell_client_identity")], F.lit("Unknown")))
    df = df.withColumn("buy_algo_type", F.coalesce(a_map[F.col("buy_algo_indicator")], F.lit("Unknown")))
    df = df.withColumn("sell_algo_type", F.coalesce(a_map[F.col("sell_algo_indicator")], F.lit("Unknown")))
    df = df.withColumn("liquidity_group", F.when(F.col("symbol").isin(LIQUID_SYMBOLS), "Liquid").otherwise("Illiquid"))

    df.write.mode("overwrite").partitionBy("trade_date").parquet(out_path)
    print(f"[DONE] Enriched CASH Trades saved to {out_path}")
