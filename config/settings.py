"""Central configuration for the NSE expiry-day microstructure pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

# System paths. Derived from this file's own location rather than hard-coded, so the
# repository can be cloned anywhere - the previous absolute `c:\sandbox\ProjectCourse`
# made every path in the pipeline wrong on any other machine.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PARSED_DATA_DIR = PROJECT_ROOT / "data" / "parsed"
ENRICHED_DATA_DIR = PROJECT_ROOT / "data" / "enriched"
CLOB_DATA_DIR = PROJECT_ROOT / "data" / "clob_snapshots"
# Raw nsetick book output, kept apart from the flattened snapshots the analyses read: the
# stage-5 queries glob the snapshot root recursively, and a second schema underneath it
# would be unioned into every one of them.
CLOB_BOOKS_DIR = PROJECT_ROOT / "data" / "clob_books"
BLOOMBERG_DATA_DIR = PROJECT_ROOT / "data" / "bloomberg"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
LOG_DIR = PROJECT_ROOT / "logs"

for path in (RAW_DATA_DIR, PARSED_DATA_DIR, ENRICHED_DATA_DIR, CLOB_DATA_DIR,
             CLOB_BOOKS_DIR, BLOOMBERG_DATA_DIR, RESULTS_DIR, LOG_DIR):
    path.mkdir(parents=True, exist_ok=True)

# Target equity universe.
#
# Plain symbols, no padding. NSE right-aligns the 10-byte symbol field with 'b' (0x62)
# padding, and the previous configuration carried pre-padded literals such as "  RELIANCE"
# so that a SUBSTRING comparison would match. That coupling between the universe and the
# byte layout is what five successive commits in this repository's history were trying to
# repair. nsetick strips the padding during decode, so the filter now compares symbols.
TARGET_SYMBOLS: List[str] = [
    "RELIANCE", "TCS", "ICICIBANK", "HDFCBANK", "INFY",
    "DIVISLAB", "CIPLA", "EICHERMOT", "BPCL", "APOLLOHOSP",
]
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

# Target sessions, named as NSE names its files: DDMMYYYY.
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

# Trading session windows (IST). NSE timestamps are IST wall clock with no zone attached,
# so these are compared against the time-of-day component directly.
SETTLEMENT_WINDOW_START = "15:00:00"
SETTLEMENT_WINDOW_END = "15:30:00"
MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"

CASH_SERIES_FILTER = "EQ"
FUTURES_INSTRUMENT_FILTER = "FUTSTK"

# Limit order book reconstruction.
#
# Twenty levels rather than ten. Depth erosion during settlement is the point of stage 5,
# and on a thin name the visible book empties past level five well before 15:30 - a
# ten-level snapshot records that as a floor of zeros and cannot distinguish a book that is
# merely thin from one that has gone. The extra levels cost one column triple each.
CLOB_SNAPSHOT_INTERVAL_SECONDS = 1.0
CLOB_DEPTH_LEVELS = 20

# Levels carried into the flattened snapshot the stage-5 analyses read. Kept at ten so the
# existing `bid_depth_1..10` contract is unchanged; the deeper levels remain available in
# the raw nsetick snapshots alongside it.
CLOB_REPORTED_LEVELS = 10

# Threads handed to the Rust parser and book builder. None lets nsetick size to the machine.
NSETICK_THREADS: int | None = None
