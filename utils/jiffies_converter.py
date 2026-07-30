"""
Convert NSE Jiffies timestamp to Python/PySpark datetime.
Jiffies: 65536 jiffies = 1 second, epoch = 1 Jan 1980 00:00:00 UTC.
"""
from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType
from config.settings import JIFFIES_PER_SECOND, EPOCH_OFFSET_SECONDS

def add_datetime_column(df, jiffies_col="txn_time_jiffies", output_col="txn_datetime"):
    """Add a timestamp column by converting jiffies to datetime."""
    return df.withColumn(
        output_col,
        F.from_unixtime(
            F.col(jiffies_col).cast("double") / JIFFIES_PER_SECOND + EPOCH_OFFSET_SECONDS
        ).cast(TimestampType())
    )

def jiffies_to_seconds_since_epoch(jiffies_value):
    """Pure Python version for use in CLOB builder."""
    return jiffies_value / JIFFIES_PER_SECOND + EPOCH_OFFSET_SECONDS
