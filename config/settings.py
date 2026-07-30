"""
settings.py — Project constants and configuration.
Single source of truth for paths, symbols, dates, Spark configs, and options.
"""
import os

# === PATHS ===
PROJECT_ROOT = r"c:\sandbox\ProjectCourse"
RAW_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
PARSED_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "parsed")
ENRICHED_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "enriched")
CLOB_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "clob_snapshots")
BLOOMBERG_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "bloomberg")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "data", "results")

# Ensure required output directories exist
for path in [RAW_DATA_DIR, PARSED_DATA_DIR, ENRICHED_DATA_DIR, CLOB_DATA_DIR, BLOOMBERG_DATA_DIR, RESULTS_DIR]:
    os.makedirs(path, exist_ok=True)

# === SPARK CONFIG (24 GB RAM machine) ===
SPARK_DRIVER_MEMORY = "16g"
SPARK_EXECUTOR_MEMORY = "16g"
SPARK_SQL_SHUFFLE_PARTITIONS = 8
SPARK_LOCAL_DIR = os.path.join(PROJECT_ROOT, "data", "spark_tmp")
os.makedirs(SPARK_LOCAL_DIR, exist_ok=True)

# === TARGET SYMBOLS (10-char padded as in raw data) ===
TARGET_SYMBOLS_RAW = [
    "  RELIANCE", "       TCS", " ICICIBANK", "  HDFCBANK", "      INFY",
    "   DIVISLAB", "     CIPLA", " EICHERMOT", "      BPCL", "APOLLOHOSP",
]
TARGET_SYMBOLS = [s.strip() for s in TARGET_SYMBOLS_RAW]

LIQUID_SYMBOLS = ["RELIANCE", "TCS", "ICICIBANK", "HDFCBANK", "INFY"]
ILLIQUID_SYMBOLS = ["DIVISLAB", "CIPLA", "EICHERMOT", "BPCL", "APOLLOHOSP"]

# === BLOOMBERG TICKER MAPPING ===
BLOOMBERG_TICKERS = {
    "RELIANCE":   ("RELI1! IN Equity",  "RELI2! IN Equity",  "RELIANCE IN Equity"),
    "TCS":        ("TCS1! IN Equity",   "TCS2! IN Equity",   "TCS IN Equity"),
    "ICICIBANK":  ("ICICIBC1! IN Equity","ICICIBC2! IN Equity","ICICIBANK IN Equity"),
    "HDFCBANK":   ("HDFCB1! IN Equity", "HDFCB2! IN Equity", "HDFCBANK IN Equity"),
    "INFY":       ("INFO1! IN Equity",  "INFO2! IN Equity",  "INFOSYS IN Equity"),
    "DIVISLAB":   ("DIVI1! IN Equity",  "DIVI2! IN Equity",  "DIVISLAB IN Equity"),
    "CIPLA":      ("CIPL1! IN Equity",  "CIPL2! IN Equity",  "CIPLA IN Equity"),
    "EICHERMOT":  ("EIM1! IN Equity",   "EIM2! IN Equity",   "EICHERMOT IN Equity"),
    "BPCL":       ("BPCL1! IN Equity",  "BPCL2! IN Equity",  "BPCL IN Equity"),
    "APOLLOHOSP": ("APHS1! IN Equity",  "APHS2! IN Equity",  "APOLLOHOSP IN Equity"),
}

# === TARGET DATES ===
EXPIRY_THURSDAYS_DDMMYYYY = [
    "27012022", "24022022", "31032022", "28042022",
    "26052022", "30062022", "28072022", "25082022",
    "29092022", "27102022", "24112022", "29122022",
]
CONTROL_DAYS_DDMMYYYY = [
    "25012022",  # 26-Jan is Republic Day → use Tuesday 25th
    "23022022", "30032022", "27042022",
    "25052022", "29062022", "27072022", "24082022",
    "28092022",
    "25102022",  # 26-Oct is Diwali → use Tuesday 25th
    "23112022", "28122022",
]
ALL_TARGET_DATES = EXPIRY_THURSDAYS_DDMMYYYY + CONTROL_DAYS_DDMMYYYY

# Map each expiry to its control day (for paired statistical tests)
EXPIRY_CONTROL_PAIRS = list(zip(EXPIRY_THURSDAYS_DDMMYYYY, CONTROL_DAYS_DDMMYYYY))

# Bloomberg date range for roll analysis
BLOOMBERG_START_DATE = "2022-01-17"
BLOOMBERG_END_DATE = "2022-12-30"

# === JIFFIES CONVERSION ===
JIFFIES_PER_SECOND = 65536
JIFFIES_EPOCH = "1980-01-01 00:00:00"
EPOCH_OFFSET_SECONDS = 315532800  # seconds from 1970-01-01 to 1980-01-01

# === SETTLEMENT WINDOW ===
SETTLEMENT_WINDOW_START = "15:00:00"  # 3:00 PM IST
SETTLEMENT_WINDOW_END   = "15:30:00"  # 3:30 PM IST
MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"

# === CASH MARKET: SERIES FILTER ===
CASH_SERIES_FILTER = "EQ"

# === CLOB CONFIG ===
CLOB_SNAPSHOT_INTERVAL_SECONDS = 1
CLOB_DEPTH_LEVELS = 10
CLOB_PARALLEL_WORKERS = 6
