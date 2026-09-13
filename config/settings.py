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

# The manuscript is LaTeX source, authored and edited as LaTeX. The pipeline writes only
# what it computes - macros, tables, figures - into paper/generated and paper/figures, and
# never touches the prose. Generating the document from Python string constants, which is
# what this replaced, meant no editor support, escaping every backslash twice, and no way to
# place a float where it belongs.
PAPER_DIR = PROJECT_ROOT / "paper"
PAPER_GENERATED_DIR = PAPER_DIR / "generated"
PAPER_FIGURES_DIR = PAPER_DIR / "figures"
LOG_DIR = PROJECT_ROOT / "logs"

for path in (RAW_DATA_DIR, PARSED_DATA_DIR, ENRICHED_DATA_DIR, CLOB_DATA_DIR,
             CLOB_BOOKS_DIR, BLOOMBERG_DATA_DIR, RESULTS_DIR, LOG_DIR,
             PAPER_GENERATED_DIR, PAPER_FIGURES_DIR):
    path.mkdir(parents=True, exist_ok=True)

# Target equity universe.
#
# Membership, grouping and the reasoning behind the three-group design live in
# config/universe.py, which prefers a universe derived from the tape by
# scripts/build_universe.py over its checked-in fallback lists. Re-exported here so the
# analysis modules keep a single import.
from config.universe import (  # noqa: E402,F401
    DERIVATIVE_SYMBOLS,
    GROUPS,
    ILLIQUID_SYMBOLS,
    LIQUID_SYMBOLS,
    PLACEBO_SYMBOLS,
    TARGET_SYMBOLS,
    group_of,
    is_derived_universe,
)

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

# Levels carried into the flattened snapshot the analysis stages read.
#
# All twenty. Ten was chosen to preserve an older `bid_depth_1..10` contract, but the
# book-walk measures need enough of the book to absorb a realistic order: at ten levels a
# ten-basis-point move was unreachable in over ninety per cent of snapshots, so every cost
# figure was censored. The depth totals the stage-5 analyses report stay on the first ten
# levels, which is what they have always meant.
CLOB_REPORTED_LEVELS = 20
CLOB_DEPTH_SUM_LEVELS = 10

# Parquet compression for every layer the pipeline writes.
#
# zstd at level 3, not snappy. Measured on a real order partition: 113.5 MB snappy against
# 73.9 MB zstd, a factor of 1.54, and level 9 buys only another 2 per cent for half again the
# write time. Across both projects that is roughly ninety gigabytes, which is the difference
# between fitting on a 500 GB allocation and not.
#
# The cost is on the read side, and it is small: a warm-cache scan of the same partition took
# 0.13 s under snappy and 0.14 s under zstd. Against that, a cold read moves 35 per cent
# fewer bytes, so on anything disk-bound zstd is the faster of the two.
PARQUET_COMPRESSION = "zstd"

# Threads handed to the Rust parser and book builder. None lets nsetick size to the machine.
NSETICK_THREADS: int | None = None
