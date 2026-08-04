"""Central configuration for NSE expiry day microstructure pipeline."""

from pathlib import Path
from typing import Dict, List, Tuple

# System paths
PROJECT_ROOT = Path(r"c:\sandbox\ProjectCourse")
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PARSED_DATA_DIR = PROJECT_ROOT / "data" / "parsed"
ENRICHED_DATA_DIR = PROJECT_ROOT / "data" / "enriched"
CLOB_DATA_DIR = PROJECT_ROOT / "data" / "clob_snapshots"
BLOOMBERG_DATA_DIR = PROJECT_ROOT / "data" / "bloomberg"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

for path in (RAW_DATA_DIR, PARSED_DATA_DIR, ENRICHED_DATA_DIR, CLOB_DATA_DIR, BLOOMBERG_DATA_DIR, RESULTS_DIR):
    path.mkdir(parents=True, exist_ok=True)

# Target equity universe
TARGET_SYMBOLS_RAW: List[str] = [
    "  RELIANCE", "       TCS", " ICICIBANK", "  HDFCBANK", "      INFY",
    "   DIVISLAB", "     CIPLA", " EICHERMOT", "      BPCL", "APOLLOHOSP",
]
TARGET_SYMBOLS: List[str] = [symbol.strip() for symbol in TARGET_SYMBOLS_RAW]
LIQUID_SYMBOLS: List[str] = ["RELIANCE", "TCS", "ICICIBANK", "HDFCBANK", "INFY"]
ILLIQUID_SYMBOLS: List[str] = ["DIVISLAB", "CIPLA", "EICHERMOT", "BPCL", "APOLLOHOSP"]

# Bloomberg ticker mapping (Near Fut, Next Fut, Spot Equity)
BLOOMBERG_TICKERS: Dict[str, Tuple[str, str, str]] = {
    "RELIANCE":   ("RELI1! IN Equity",   "RELI2! IN Equity",   "RELIANCE IN Equity"),
    "TCS":        ("TCS1! IN Equity",    "TCS2! IN Equity",    "TCS IN Equity"),
    "ICICIBANK":  ("ICICIBC1! IN Equity","ICICIBC2! IN Equity","ICICIBANK IN Equity"),
    "HDFCBANK":   ("HDFCB1! IN Equity",  "HDFCB2! IN Equity",  "HDFCBANK IN Equity"),
    "INFY":       ("INFO1! IN Equity",   "INFO2! IN Equity",   "INFOSYS IN Equity"),
    "DIVISLAB":   ("DIVI1! IN Equity",   "DIVI2! IN Equity",   "DIVISLAB IN Equity"),
    "CIPLA":      ("CIPL1! IN Equity",   "CIPL2! IN Equity",   "CIPLA IN Equity"),
    "EICHERMOT":  ("EIM1! IN Equity",    "EIM2! IN Equity",    "EICHERMOT IN Equity"),
    "BPCL":       ("BPCL1! IN Equity",   "BPCL2! IN Equity",   "BPCL IN Equity"),
    "APOLLOHOSP": ("APHS1! IN Equity",   "APHS2! IN Equity",   "APOLLOHOSP IN Equity"),
}

# Target date pairs (Expiry Thursdays and paired Control days)
EXPIRY_THURSDAYS_DDMMYYYY: List[str] = [
    "27012022", "24022022", "31032022", "28042022",
    "26052022", "30062022", "28072022", "25082022",
    "29092022", "27102022", "24112022", "29122022",
]
CONTROL_DAYS_DDMMYYYY: List[str] = [
    "25012022", "23022022", "30032022", "27042022",
    "25052022", "29062022", "27072022", "24082022",
    "28092022", "25102022", "23112022", "28122022",
]
ALL_TARGET_DATES: List[str] = EXPIRY_THURSDAYS_DDMMYYYY + CONTROL_DAYS_DDMMYYYY
EXPIRY_CONTROL_PAIRS: List[Tuple[str, str]] = list(zip(EXPIRY_THURSDAYS_DDMMYYYY, CONTROL_DAYS_DDMMYYYY))

BLOOMBERG_START_DATE = "2022-01-17"
BLOOMBERG_END_DATE = "2022-12-30"

# NSE Tick Jiffies epoch conversion
JIFFIES_PER_SECOND = 65536
JIFFIES_EPOCH = "1980-01-01 00:00:00"
EPOCH_OFFSET_SECONDS = 315532800

# Trading session windows (IST)
SETTLEMENT_WINDOW_START = "15:00:00"
SETTLEMENT_WINDOW_END = "15:30:00"
MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"

CASH_SERIES_FILTER = "EQ"
FUTURES_INSTRUMENT_FILTER = "FUTSTK"

# CLOB parameters
CLOB_SNAPSHOT_INTERVAL_SECONDS = 1
CLOB_DEPTH_LEVELS = 10
CLOB_PARALLEL_WORKERS = 6
