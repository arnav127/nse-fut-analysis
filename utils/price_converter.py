"""
Convert NSE fixed-width price fields from paise-encoding to rupees.
CASH and FAO: rightmost 2 digits are decimal → divide by 100.
"""
from pyspark.sql import functions as F

def paise_to_rupees(df, col_name, decimal_places=2):
    """Convert a paise-encoded integer column to rupees (float)."""
    divisor = 10 ** decimal_places
    return df.withColumn(col_name, F.col(col_name).cast("double") / divisor)
