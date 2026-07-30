"""
Create and configure local SparkSession.
"""
from pyspark.sql import SparkSession
from config.settings import (
    SPARK_DRIVER_MEMORY, SPARK_SQL_SHUFFLE_PARTITIONS, SPARK_LOCAL_DIR
)

def get_spark(app_name="NSE_ExpiryDayAnalysis"):
    return (
        SparkSession.builder
        .master("local[*]")
        .appName(app_name)
        .config("spark.driver.memory", SPARK_DRIVER_MEMORY)
        .config("spark.sql.shuffle.partitions", str(SPARK_SQL_SHUFFLE_PARTITIONS))
        .config("spark.local.dir", SPARK_LOCAL_DIR)
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.driver.maxResultSize", "4g")
        .getOrCreate()
    )
