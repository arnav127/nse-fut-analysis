# Expiry Day Dynamics & VWAP Settlement Anomalies — Implementation Plan

## Project Summary

Analyze NSE tick-level order and trade data (CASH + FAO segments) for the 12 monthly expiry Thursdays of 2022 (+ 12 control days) to detect VWAP settlement anomalies in the final 30 minutes of trading. Focus on 10 Nifty 50 stocks (5 liquid + 5 illiquid) and their corresponding FUTSTK futures. Augment with Bloomberg terminal data for roll pressure directionality and cost-of-carry context.

**Hardware**: i7 8th gen, 24 GB RAM, M150 GPU (GPU won't be used — PySpark runs on CPU/RAM).

**Stack**: Python 3.x + PySpark (local mode) + Parquet for intermediate storage. Pure Python + `sortedcontainers` for CLOB reconstruction. Bloomberg Terminal (Excel/BQL) for roll and spread data.

> [!IMPORTANT]
> PySpark local mode with 24 GB RAM means we must be very careful about memory. The FAO files can be 50–70 GB compressed. We will **filter aggressively at parse-time** (only target symbols, only target dates) and never load full files into memory.

---

## Architecture Overview

```
Bloomberg Terminal                           Raw .DAT.gz files (NSE)
       │                                            │
       ▼                                            ▼
┌──────────────────────┐               ┌──────────────────────┐
│ STAGE 0B: BLOOMBERG  │               │  STAGE 1: PARSE      │
│ Roll spread, OI,     │               │  Fixed-width → Parq  │
│ cost-of-carry, basis │               │  Filter symbols/dates│
└──────────────────────┘               └──────────────────────┘
       │                                            │
       ▼                                            ▼
┌──────────────────────┐               ┌──────────────────────┐
│ bloomberg_data/      │               │  STAGE 2: ENRICH     │
│   roll_spreads.csv   │               │  Jiffies → datetime  │
│   open_interest.csv  │               │  paise → rupees      │
│   cost_of_carry.csv  │               │  labels, flags       │
└──────────────────────┘               └──────────────────────┘
       │                                    │             │
       │                    ┌───────────────┘             │
       │                    ▼                             ▼
       │       ┌──────────────────────┐     ┌──────────────────────────┐
       │       │  STAGE 3: TRADE-LEVEL│     │  STAGE 4: CLOB           │
       │       │  ANALYSIS (7 modules)│     │  RECONSTRUCTION          │
       │       └──────────────────────┘     └──────────────────────────┘
       │                    │                             │
       │                    ▼                             ▼
       │       ┌──────────────────────────────────────────────────┐
       │       │  STAGE 5: CLOB-BASED ANALYSIS (5 modules)       │
       │       └──────────────────────────────────────────────────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│  STAGE 6: BLOOMBERG-INTEGRATED ANALYSIS (3 modules)         │
│  Roll direction × VWAP drift, cost-of-carry breakdown,      │
│  cross-market signal validation                              │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  STAGE 7: CONSOLIDATED REPORT                                │
│  All 23 hypotheses, statistical tests, charts                │
└──────────────────────────────────────────────────────────────┘
```

---

## Target Dates (2022 Monthly Expiry Thursdays + Control Days)

Rule: Control day = the trading day immediately before the expiry Thursday (usually Wednesday). If that day is a market holiday, use the preceding trading day.

| Month | Expiry Thursday | Control Day | Notes |
|-------|-----------------|-------------|-------|
| Jan   | 27-01-2022      | 25-01-2022  | 26-Jan is Republic Day (holiday) → use Tuesday 25th |
| Feb   | 24-02-2022      | 23-02-2022  | |
| Mar   | 31-03-2022      | 30-03-2022  | |
| Apr   | 28-04-2022      | 27-04-2022  | |
| May   | 26-05-2022      | 25-05-2022  | |
| Jun   | 30-06-2022      | 29-06-2022  | |
| Jul   | 28-07-2022      | 27-07-2022  | |
| Aug   | 25-08-2022      | 24-08-2022  | |
| Sep   | 29-09-2022      | 28-09-2022  | |
| Oct   | 27-10-2022      | 25-10-2022  | 26-Oct is Diwali (holiday) → use Tuesday 25th |
| Nov   | 24-11-2022      | 23-11-2022  | |
| Dec   | 29-12-2022      | 28-12-2022  | |

## Target Symbols (10 Nifty 50 Constituents of 2022)

### 5 Most Liquid (by avg daily traded value in 2022)
| # | Symbol     | Lot Size (2022) | Bloomberg Ticker (generic futures) |
|---|------------|-----------------|-------------------------------------|
| 1 | RELIANCE   | 250             | RELI1! IN Equity / RELI2! IN Equity |
| 2 | TCS        | 150             | TCS1! IN Equity / TCS2! IN Equity   |
| 3 | ICICIBANK  | 1375            | ICICIBC1! IN / ICICIBC2! IN         |
| 4 | HDFCBANK   | 550             | HDFCB1! IN / HDFCB2! IN            |
| 5 | INFY       | 300             | INFO1! IN / INFO2! IN               |

### 5 Least Liquid (among Nifty 50 by avg daily traded value in 2022)
| # | Symbol     | Lot Size (2022) | Bloomberg Ticker (generic futures) |
|---|------------|-----------------|-------------------------------------|
| 6 | DIVISLAB    | 100            | DIVI1! IN / DIVI2! IN              |
| 7 | CIPLA       | 650            | CIPL1! IN / CIPL2! IN              |
| 8 | EICHERMOT   | 350            | EIM1! IN / EIM2! IN                |
| 9 | BPCL        | 1800           | BPCL1! IN / BPCL2! IN             |
| 10| APOLLOHOSP | 125            | APHS1! IN / APHS2! IN             |

> [!NOTE]
> Bloomberg tickers above are indicative — verify exact generic futures tickers in your terminal. The `1!` suffix = front-month generic, `2!` = second-month generic.

---

## Proposed Project Directory Structure

```
c:\sandbox\ProjectCourse\
├── config/
│   ├── settings.py              # All constants: symbols, dates, paths, Spark config
│   └── schema_definitions.py    # Fixed-width field schemas for all 4 file types
│
├── stage1_parse/
│   ├── parse_cash_orders.py     # CASH Orders .DAT.gz → Parquet
│   ├── parse_cash_trades.py     # CASH Trades .DAT.gz → Parquet
│   ├── parse_fao_orders.py      # FAO Orders .DAT.gz → Parquet
│   ├── parse_fao_trades.py      # FAO Trades .DAT.gz → Parquet
│   └── run_parse_all.py         # Orchestrator: loop over dates, call parsers
│
├── stage2_enrich/
│   ├── enrich_cash.py           # Add datetime, rupee prices, time buckets, flags
│   ├── enrich_fao.py            # Same for FAO, plus filter FUTSTK only
│   └── run_enrich_all.py        # Orchestrator
│
├── stage3_analysis/
│   ├── a1_vwap_trajectory.py    # Minute-by-minute VWAP for cash + futures basis
│   ├── a2_basis_divergence.py   # Cash-FUTSTK basis volatility, statistical tests
│   ├── a3_participant_profile.py# Volume/trades by Client Identity Flag
│   ├── a4_algo_segmentation.py  # Algo vs Non-Algo order flow analysis
│   ├── a5_cancellation_patterns.py # Spoofing: cancel-to-entry ratios
│   ├── a6_iceberg_detection.py  # Order Qty vs Disclosed Qty analysis
│   ├── a7_ioc_aggressiveness.py # IOC/Market order analysis in settlement window
│   └── run_all_analysis.py      # Orchestrator
│
├── stage4_clob/
│   ├── order_book.py            # OrderBook class (sortedcontainers-based)
│   ├── clob_builder.py          # Replay orders → build book → snapshot
│   ├── run_clob_all.py          # Orchestrator with multiprocessing
│   └── clob_schemas.py          # Snapshot DataFrame schema
│
├── stage5_clob_analysis/
│   ├── b1_spread_dynamics.py    # Bid-ask spread evolution during settlement
│   ├── b2_depth_erosion.py      # Depth at best N levels over time
│   ├── b3_order_flow_imbalance.py # Net buy vs sell pressure
│   ├── b4_price_impact.py       # How aggressive orders move the midpoint
│   ├── b5_book_asymmetry.py     # Bid-side vs ask-side volume ratios
│   └── run_clob_analysis.py     # Orchestrator
│
├── stage6_bloomberg/
│   ├── bloomberg_data_guide.md  # Instructions for pulling data from terminal
│   ├── load_bloomberg_data.py   # Read exported CSVs into DataFrames
│   ├── c1_roll_pressure.py      # Long/short roll direction from spread + OI
│   ├── c2_cost_of_carry.py      # Implied CoC and fair-value basis
│   ├── c3_directional_validation.py # Cross-reference roll direction with VWAP drift
│   └── run_bloomberg_analysis.py
│
├── stage7_report/
│   ├── stat_tests.py            # All hypothesis tests in one place
│   ├── generate_charts.py       # Publication-quality matplotlib/seaborn charts
│   └── generate_report.py       # Combine results into summary tables
│
├── utils/
│   ├── spark_session.py         # Create & configure local SparkSession
│   ├── jiffies_converter.py     # Jiffies ↔ datetime conversion
│   └── price_converter.py       # Paise → Rupees with correct decimal places
│
├── data/
│   ├── raw/                     # Place .DAT.gz files here
│   ├── parsed/                  # Stage 1 output (Parquet)
│   ├── enriched/                # Stage 2 output (Parquet)
│   ├── clob_snapshots/          # Stage 4 output (Parquet, per symbol-date)
│   ├── bloomberg/               # Bloomberg exported CSVs
│   └── results/                 # Stage 3/5/6/7 output (CSV, PNG)
│
├── main.py                      # Master pipeline runner
├── requirements.txt
└── README.md
```

---

## STAGE 0A: Environment & Configuration

### Task 0.1 — `requirements.txt`

```
pyspark==3.5.1
pandas>=2.0
matplotlib>=3.7
seaborn>=0.12
pyarrow>=14.0
sortedcontainers>=2.4
scipy>=1.11
statsmodels>=0.14
```

### Task 0.2 — `config/settings.py`

Create a Python file containing ALL project constants. This is the **single source of truth** for every other script.

```python
"""
settings.py — Project constants and configuration.
Every other script imports from here. Change nothing else when adjusting scope.
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

# === SPARK CONFIG (24 GB RAM machine) ===
SPARK_DRIVER_MEMORY = "16g"
SPARK_EXECUTOR_MEMORY = "16g"
SPARK_SQL_SHUFFLE_PARTITIONS = 8
SPARK_LOCAL_DIR = os.path.join(PROJECT_ROOT, "data", "spark_tmp")

# === TARGET SYMBOLS (10-char padded as in raw data) ===
TARGET_SYMBOLS_RAW = [
    "  RELIANCE", "       TCS", " ICICIBANK", "  HDFCBANK", "      INFY",
    "   DIVISLAB", "     CIPLA", " EICHERMOT", "      BPCL", "APOLLOHOSP",
]
TARGET_SYMBOLS = [s.strip() for s in TARGET_SYMBOLS_RAW]

LIQUID_SYMBOLS = ["RELIANCE", "TCS", "ICICIBANK", "HDFCBANK", "INFY"]
ILLIQUID_SYMBOLS = ["DIVISLAB", "CIPLA", "EICHERMOT", "BPCL", "APOLLOHOSP"]

# === BLOOMBERG TICKER MAPPING ===
# Maps NSE symbol → (front-month generic ticker, second-month generic ticker, spot ticker)
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

# Bloomberg date range for roll analysis (need ~5 trading days before each expiry)
BLOOMBERG_START_DATE = "2022-01-17"  # ~10 days before first expiry
BLOOMBERG_END_DATE = "2022-12-30"   # day after last expiry

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
CLOB_PARALLEL_WORKERS = 6  # Leave 2 cores for OS (i7 = 8 threads)
```

### Task 0.3 — `config/schema_definitions.py`

Define the **exact fixed-width field layouts** for each of the 4 file types. These are the schemas that the parsers use to slice each line.

```python
"""
schema_definitions.py — NSE Historical Data fixed-width record layouts.
Each schema is a list of (field_name, start_pos, length, data_type) tuples.
Positions are 0-indexed. data_type is 'str', 'int', or 'long'.

Source: NSE_Hist_Order_data_layout_1.10_0.pdf, Version 1.10
"""

# ============================================================
# 1. CASH (CM) ORDERS — Total record length: 87 bytes + LF
# ============================================================
CM_ORDERS_SCHEMA = [
    ("record_indicator",   0,  2, "str"),   # RM or PO
    ("segment",            2,  4, "str"),   # CASH
    ("order_number",       6, 16, "long"),
    ("txn_time_jiffies",  22, 14, "long"),
    ("buy_sell",          36,  1, "str"),   # B or S
    ("activity_type",     37,  1, "int"),   # 1=Entry, 3=Cancel, 4=Mod
    ("symbol",            38, 10, "str"),   # left-padded with spaces
    ("series",            48,  2, "str"),   # EQ, BE, etc.
    ("volume_disclosed",  50,  8, "long"),
    ("volume_original",   58,  8, "long"),
    ("limit_price",       66,  8, "long"),  # paise, last 2 digits = decimal
    ("trigger_price",     74,  8, "long"),  # paise, last 2 digits = decimal
    ("mkt_order_flag",    82,  1, "str"),   # Y=Market, N=Limit
    ("stop_loss_flag",    83,  1, "str"),   # Y/N
    ("ioc_flag",          84,  1, "str"),   # Y/N
    ("algo_indicator",    85,  1, "int"),   # 0=Algo,1=NonAlgo,2=AlgoSOR,3=NonAlgoSOR
    ("client_identity",   86,  1, "int"),   # 1=CP(Custodian),2=Prop,3=NCNP
]
CM_ORDERS_RECORD_LENGTH = 87

# ============================================================
# 2. CASH (CM) TRADES — Total record length: 100 bytes + LF
# ============================================================
CM_TRADES_SCHEMA = [
    ("record_indicator",       0,  2, "str"),
    ("segment",                2,  4, "str"),
    ("trade_number",           6, 16, "long"),
    ("txn_time_jiffies",      22, 14, "long"),
    ("symbol",                36, 10, "str"),
    ("series",                46,  2, "str"),
    ("trade_price",           48,  8, "long"),  # paise, last 2 = decimal
    ("trade_quantity",        56,  8, "long"),
    ("buy_order_number",      64, 16, "long"),
    ("buy_algo_indicator",    80,  1, "int"),
    ("buy_client_identity",   81,  1, "int"),
    ("sell_order_number",     82, 16, "long"),
    ("sell_algo_indicator",   98,  1, "int"),
    ("sell_client_identity",  99,  1, "int"),
]
CM_TRADES_RECORD_LENGTH = 100

# ============================================================
# 3. FAO ORDERS — Total record length: 112 bytes + LF
# ============================================================
FAO_ORDERS_SCHEMA = [
    ("record_indicator",   0,  2, "str"),
    ("segment",            2,  4, "str"),   # "FAO "
    ("order_number",       6, 16, "long"),
    ("txn_time_jiffies",  22, 14, "long"),
    ("buy_sell",          36,  1, "str"),
    ("activity_type",     37,  1, "int"),   # 1=Entry, 3=Cancel, 4=Mod
    ("symbol",            38, 10, "str"),
    ("instrument",        48,  6, "str"),   # FUTSTK, OPTSTK, FUTIDX, OPTIDX
    ("expiry_date",       54,  9, "str"),   # ddMMMyyyy e.g. "28JUN2012"
    ("strike_price",      63,  8, "long"),  # paise, last 2 = decimal. 0 for futures
    ("option_type",       71,  2, "str"),   # CE, PE, CA, PA, FF
    ("volume_disclosed",  73,  8, "long"),
    ("volume_original",   81,  8, "long"),
    ("limit_price",       89,  8, "long"),  # paise, last 2 = decimal
    ("trigger_price",     97,  8, "long"),
    ("mkt_order_flag",   105,  1, "str"),
    ("stop_loss_flag",   106,  1, "str"),
    ("ioc_flag",         107,  1, "str"),
    ("spread_type",      108,  1, "str"),   # S, 2, 3, *
    ("algo_indicator",   109,  1, "int"),
    ("client_identity",  110,  1, "int"),
    ("limit_price_ind",  111,  1, "str"),   # Y=Positive, N=Negative
]
FAO_ORDERS_RECORD_LENGTH = 112

# ============================================================
# 4. FAO TRADES — Total record length: 124 bytes + LF
#    (Post Sep-2020: trade_number is 17 bytes)
# ============================================================
FAO_TRADES_SCHEMA = [
    ("record_indicator",       0,  2, "str"),
    ("segment",                2,  4, "str"),   # "FAO "
    ("trade_number",           6, 17, "long"),  # 17 bytes post Sep-2020
    ("txn_time_jiffies",      23, 14, "long"),
    ("symbol",                37, 10, "str"),
    ("instrument",            47,  6, "str"),
    ("expiry_date",           53,  9, "str"),
    ("strike_price",          62,  8, "long"),
    ("option_type",           70,  2, "str"),
    ("trade_price",           72,  8, "long"),  # paise, last 2 = decimal
    ("trade_quantity",        80,  8, "long"),
    ("buy_order_number",      88, 16, "long"),
    ("buy_algo_indicator",   104,  1, "int"),
    ("buy_client_identity",  105,  1, "int"),
    ("sell_order_number",    106, 16, "long"),
    ("sell_algo_indicator",  122,  1, "int"),
    ("sell_client_identity", 123,  1, "int"),
]
FAO_TRADES_RECORD_LENGTH = 124
```

### Task 0.4 — `utils/spark_session.py`

```python
"""
Create a configured local SparkSession.
Call get_spark() from any script that needs Spark.
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
```

### Task 0.5 — `utils/jiffies_converter.py`

```python
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
```

> [!IMPORTANT]
> The epoch offset (315532800 seconds) = 3652 days × 86400 sec. Covers 1970→1980 with leap years 1972, 1976. **Validate against a known trade timestamp from NSE bhavcopy on first run.**

### Task 0.6 — `utils/price_converter.py`

```python
"""
Convert NSE fixed-width price fields from paise-encoding to rupees.
CASH and FAO: rightmost 2 digits are decimal → divide by 100.
"""
from pyspark.sql import functions as F

def paise_to_rupees(df, col_name, decimal_places=2):
    """Convert a paise-encoded integer column to rupees (float)."""
    divisor = 10 ** decimal_places
    return df.withColumn(col_name, F.col(col_name).cast("double") / divisor)
```

---

## STAGE 0B: BLOOMBERG DATA COLLECTION

### Purpose

NSE microstructure data tells us **what** happened at the order/trade level. Bloomberg data provides the **macro context**: was this expiry dominated by long rolls or short rolls? What was the theoretical fair-value basis? This lets us determine whether settlement-window behavior was directionally consistent with roll pressure — a key indicator of deliberate settlement punching.

### Task 0B.1 — `stage6_bloomberg/bloomberg_data_guide.md`: Data Pull Instructions

This file tells the user exactly what to pull from Bloomberg Terminal. The data should be exported as CSV files into `data/bloomberg/`.

---

#### Dataset 1: Calendar Spread (Roll Spread)

**What**: The price spread between the front-month (expiring) and second-month futures for each stock, daily, for the 5 trading days leading up to each expiry.

**Bloomberg method** — use BDH (Historical Data) in Excel:
```
=BDH("<SYMBOL>1! IN Equity", "PX_LAST", "2022-01-17", "2022-12-30", "Per","D")
=BDH("<SYMBOL>2! IN Equity", "PX_LAST", "2022-01-17", "2022-12-30", "Per","D")
```

Or pull both and manually compute: `spread = near_month_price - far_month_price`

**Alternatively** — Bloomberg has calendar spread tickers for some contracts. Check availability.

**Export as**: `data/bloomberg/calendar_spreads.csv`

| Column | Description |
|--------|-------------|
| `date` | Trading date (YYYY-MM-DD) |
| `symbol` | Stock symbol |
| `near_month_price` | Front-month futures closing price |
| `far_month_price` | Second-month futures closing price |
| `calendar_spread` | near - far (positive = contango, negative = backwardation) |

---

#### Dataset 2: Open Interest by Expiry

**What**: Daily open interest for the near-month and far-month FUTSTK contracts. The migration of OI from near to far month in the days before expiry reveals roll activity.

**Bloomberg fields**:
```
Fields: FUT_CUR_GEN_OPEN_INT (or OPEN_INT)
Tickers: <SYMBOL>1! IN Equity, <SYMBOL>2! IN Equity
```

**Export as**: `data/bloomberg/open_interest.csv`

| Column | Description |
|--------|-------------|
| `date` | Trading date |
| `symbol` | Stock symbol |
| `near_month_oi` | Near-month OI (number of contracts or lots) |
| `far_month_oi` | Far-month OI |
| `total_oi` | near + far |
| `near_month_oi_pct` | near / total (should decline as rolls happen) |

---

#### Dataset 3: Cost of Carry / Basis

**What**: The theoretical cost-of-carry (interest rate component) and the actual basis (futures - spot). The difference between actual basis and theoretical fair basis = **mispricing**.

**Bloomberg fields** for futures basis:
```
=BDH("<SYMBOL>1! IN Equity", "FUT_THEO_VAL, PX_LAST, FUT_BASIS", start, end)
```
For spot: `=BDH("<SYMBOL> IN Equity", "PX_LAST", start, end)`

**Or compute manually**:
```
actual_basis = futures_close - spot_close
days_to_expiry = expiry_date - current_date
annualized_basis_pct = (actual_basis / spot_close) * (365 / days_to_expiry) * 100
```

**Export as**: `data/bloomberg/cost_of_carry.csv`

| Column | Description |
|--------|-------------|
| `date` | Trading date |
| `symbol` | Stock symbol |
| `spot_close` | Cash equity closing price |
| `near_futures_close` | Near-month futures closing price |
| `actual_basis` | futures - spot (rupees) |
| `actual_basis_pct` | basis / spot × 100 |
| `days_to_expiry` | Calendar days remaining |
| `annualized_coc_pct` | Annualized cost-of-carry implied by basis |
| `risk_free_rate` | 91-day T-bill rate or MIBOR on that date (for fair value comparison) |

---

#### Dataset 4: Daily Volume (Near vs. Far Month)

**What**: Trading volume in near-month vs. far-month futures. A surge in far-month volume + decline in near-month volume = active rolling.

**Bloomberg fields**: `VOLUME` for both `<SYMBOL>1! IN Equity` and `<SYMBOL>2! IN Equity`

**Export as**: `data/bloomberg/futures_volume.csv`

| Column | Description |
|--------|-------------|
| `date` | Trading date |
| `symbol` | Stock symbol |
| `near_month_volume` | Near-month traded volume |
| `far_month_volume` | Far-month traded volume |
| `volume_ratio` | far / near (high ratio = active roll day) |

---

### Task 0B.2 — `stage6_bloomberg/load_bloomberg_data.py`

```python
"""
Load Bloomberg-exported CSV files into Pandas DataFrames.
Validate schemas, convert dates, merge into a single enriched DataFrame.
"""
import pandas as pd
from config.settings import BLOOMBERG_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def load_calendar_spreads():
    df = pd.read_csv(f"{BLOOMBERG_DATA_DIR}/calendar_spreads.csv", parse_dates=["date"])
    return df

def load_open_interest():
    df = pd.read_csv(f"{BLOOMBERG_DATA_DIR}/open_interest.csv", parse_dates=["date"])
    return df

def load_cost_of_carry():
    df = pd.read_csv(f"{BLOOMBERG_DATA_DIR}/cost_of_carry.csv", parse_dates=["date"])
    return df

def load_futures_volume():
    df = pd.read_csv(f"{BLOOMBERG_DATA_DIR}/futures_volume.csv", parse_dates=["date"])
    return df

def build_bloomberg_master():
    """Merge all Bloomberg datasets into one DataFrame keyed on (date, symbol)."""
    spreads = load_calendar_spreads()
    oi = load_open_interest()
    coc = load_cost_of_carry()
    vol = load_futures_volume()
    master = spreads.merge(oi, on=["date", "symbol"], how="outer")
    master = master.merge(coc, on=["date", "symbol"], how="outer")
    master = master.merge(vol, on=["date", "symbol"], how="outer")
    return master
```

---

## STAGE 1: PARSING (Raw .DAT.gz → Parquet)

> [!IMPORTANT]
> **Memory strategy**: Read each .DAT.gz file as a text RDD (Spark handles gzip decompression natively). Apply fixed-width slicing. Filter to target symbols IMMEDIATELY. Write to Parquet partitioned by `(date, symbol)`.

### Task 1.1 — `stage1_parse/parse_cash_orders.py`

**Purpose**: Parse `CASH_Orders_DDMMYYYY.DAT.gz` files into Parquet.

**Algorithm**:
1. Accept a single date string (`DDMMYYYY`) as argument.
2. Construct file path: `{RAW_DATA_DIR}/CASH_Orders_{date}.DAT.gz`
3. Read the file as a text RDD using `spark.sparkContext.textFile(path)`.
4. For each line, use Python string slicing based on `CM_ORDERS_SCHEMA` to extract fields.
5. Convert to a Spark DataFrame with proper column types.
6. Filter: `symbol.isin(TARGET_SYMBOLS_RAW)` AND `series == 'EQ'`.
7. Strip whitespace from `symbol` column.
8. Write to Parquet at `{PARSED_DATA_DIR}/cash_orders/date={date}/`.

**Key parsing logic (per line)**:
```python
# For each line of fixed-width text:
row = {}
for field_name, start, length, dtype in CM_ORDERS_SCHEMA:
    raw_value = line[start : start + length]
    if dtype in ("long", "int"):
        row[field_name] = int(raw_value.strip())
    else:
        row[field_name] = raw_value
```

### Task 1.2 — `stage1_parse/parse_cash_trades.py`

**Same pattern as Task 1.1** but use `CM_TRADES_SCHEMA` (record length 100). Filter by `symbol` and `series == 'EQ'`. Output: `{PARSED_DATA_DIR}/cash_trades/date={date}/`.

### Task 1.3 — `stage1_parse/parse_fao_orders.py`

**Key differences from CASH**:
- FAO files are split: glob `FAO_Orders_{date}_*.DAT.gz`.
- Use `FAO_ORDERS_SCHEMA` (record length 112).
- Filter: `symbol.isin(TARGET_SYMBOLS_RAW)` AND `instrument == 'FUTSTK'`.
- Output: `{PARSED_DATA_DIR}/fao_orders/date={date}/`.

### Task 1.4 — `stage1_parse/parse_fao_trades.py`

**Same as Task 1.3** but use `FAO_TRADES_SCHEMA` (record length 124). Filter by `symbol` and `instrument == 'FUTSTK'`. Output: `{PARSED_DATA_DIR}/fao_trades/date={date}/`.

### Task 1.5 — `stage1_parse/run_parse_all.py`

```python
"""
Loop over ALL_TARGET_DATES and run all 4 parsers for each date.
Skip dates whose output Parquet already exists (idempotent).
"""
for date in ALL_TARGET_DATES:
    parse_cash_orders(date)   # if output doesn't exist
    parse_cash_trades(date)
    parse_fao_orders(date)
    parse_fao_trades(date)
```

---

## STAGE 2: ENRICHMENT (Parquet → Enriched Parquet)

### Task 2.1 — `stage2_enrich/enrich_cash.py`

**Input**: `{PARSED_DATA_DIR}/cash_orders/` and `{PARSED_DATA_DIR}/cash_trades/`

**Transformations** (both orders and trades):

1. **Convert Jiffies to datetime**: Use `jiffies_converter.add_datetime_column()`.
2. **Extract date and time**:
   - `trade_date` = `date(txn_datetime)` → `YYYY-MM-DD`
   - `trade_time` = `time(txn_datetime)` → `HH:MM:SS.ffffff`
3. **Convert prices to rupees**: `limit_price / 100.0`, `trigger_price / 100.0`, `trade_price / 100.0`.
4. **Add 1-minute time bucket**:
   ```python
   time_bucket = concat(hour, ":", lpad(minute, 2, "0"))  # e.g. "15:01"
   ```
5. **Add `is_settlement_window`**: `True` if time >= 15:00:00 AND time <= 15:30:00.
6. **Add `is_expiry`**: `True` if date is in `EXPIRY_THURSDAYS` list.
7. **Add human-readable labels**:
   - `participant_type`: `{1: "Custodian", 2: "Proprietary", 3: "NCNP"}`
   - `algo_type`: `{0: "Algo", 1: "Non-Algo", 2: "Algo-SOR", 3: "Non-Algo-SOR"}`
   - `activity_label` (orders only): `{1: "Entry", 3: "Cancel", 4: "Modify"}`
8. **Add `liquidity_group`**: `"Liquid"` if symbol in LIQUID_SYMBOLS else `"Illiquid"`.

**Output**: `{ENRICHED_DATA_DIR}/cash_orders/` and `{ENRICHED_DATA_DIR}/cash_trades/`

### Task 2.2 — `stage2_enrich/enrich_fao.py`

**Same as Task 2.1** but for FAO data. Additional:
- Ensure `instrument == 'FUTSTK'` and `option_type == 'FF'`.
- Parse `expiry_date` string (e.g., `"28JUN2022"`) into a proper date column.
- For trades: map both buy-side and sell-side algo/client indicators to labels.

**Output**: `{ENRICHED_DATA_DIR}/fao_orders/` and `{ENRICHED_DATA_DIR}/fao_trades/`

### Task 2.3 — `stage2_enrich/run_enrich_all.py`

Orchestrator that runs both enrichment scripts.

---

## STAGE 3: TRADE-LEVEL ANALYSIS (7 Modules)

Each module reads from enriched Parquet, computes metrics, and outputs CSV + PNG to `{RESULTS_DIR}/`.

---

### Analysis A1 — `a1_vwap_trajectory.py`: VWAP Reconstruction & Trajectory

#### What We're Testing
**Hypothesis**: The cumulative VWAP during the final 30 minutes of expiry days shows abnormal deviation from the prevailing futures price, suggesting that the settlement mechanism is being gamed.

#### Algorithm
1. Load enriched CASH trades. Filter: `is_settlement_window == True`.
2. For each `(symbol, trade_date, time_bucket_1min)`:
   - **Instantaneous VWAP** = `sum(trade_price × trade_quantity) / sum(trade_quantity)` within that minute.
   - **Cumulative VWAP** = running VWAP from 15:00 to current minute (this is what NSE uses for settlement).
   - **Last traded price (LTP)** = price of the last trade in that minute.
   - **Trade count** and **total volume** per minute.
3. Load enriched FAO trades (FUTSTK). Filter: `is_settlement_window == True`.
4. Compute same minute-level metrics for futures.
5. Join on `(symbol, trade_date, time_bucket_1min)`.

#### Output Metrics
| Column | Definition |
|--------|-----------|
| `cash_cum_vwap` | Cumulative VWAP from 15:00 to this minute |
| `cash_inst_vwap` | VWAP within this 1-minute bucket |
| `cash_ltp` | Last traded price in this minute |
| `futures_avg_price` | Volume-weighted average futures trade price this minute |
| `futures_ltp` | Last traded futures price this minute |
| `basis_bps` | `((futures_avg - cash_cum_vwap) / cash_cum_vwap) × 10000` |
| `cash_volume` | Total shares traded in cash this minute |
| `futures_volume` | Total shares traded in futures this minute |

#### Charts
- **Line chart**: Cumulative VWAP vs. futures price, minute-by-minute, for each symbol on each expiry day (panel plot).
- **Overlaid**: Same chart for the paired control day in lighter color for comparison.

---

### Analysis A2 — `a2_basis_divergence.py`: Basis Volatility & Statistical Tests

#### What We're Testing
**Hypothesis H1**: Basis volatility (cash–futures spread) is significantly higher during the settlement window on expiry days than on control days.

**Hypothesis H2**: The basis divergence is more pronounced for illiquid stocks than liquid stocks (because arbitrage is harder to execute on illiquid names).

#### Algorithm
1. Use A1 output (minute-by-minute basis_bps).
2. For each `(symbol, trade_date)`, compute:
   - **Basis std dev**: Standard deviation of `basis_bps` across the 30 minutes.
   - **Basis range**: `max(basis_bps) - min(basis_bps)`.
   - **Terminal basis shift**: `basis_bps[15:30] - basis_bps[15:00]`.
   - **Basis mean absolute deviation (MAD)**.
   - **Max basis absolute value**: Peak dislocation.
3. Split into expiry vs. control groups.
4. Split by liquidity group (Liquid 5 vs. Illiquid 5).

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Paired t-test** on basis_std_dev (expiry vs. paired control, same symbol) | Test H1 |
| **Wilcoxon signed-rank test** (non-parametric alternative) | Robustness check for H1 |
| **Cohen's d** effect size | Magnitude of H1 |
| **Two-sample t-test**: liquid vs. illiquid basis_std_dev on expiry days | Test H2 |
| **Mann-Whitney U test** (non-parametric) | Robustness check for H2 |

#### Charts
- **Box plot**: Basis std dev, expiry vs. control, faceted by liquidity group.
- **Paired difference plot**: For each symbol-month, plot `(basis_vol_expiry - basis_vol_control)`.
- **Heatmap**: Basis std dev by symbol × month, color-coded.

---

### Analysis A3 — `a3_participant_profile.py`: Who Drives Expiry Volume?

#### What We're Testing
**Hypothesis H3**: Proprietary desks disproportionately increase their share of settlement-window volume on expiry days (consistent with settlement punching by informed desks).

**Hypothesis H4**: Custodian (institutional) activity patterns differ between expiry and control days in a way that reveals hedging/rolling behavior.

#### Algorithm
1. Load enriched CASH trades + FAO trades. Filter: `is_settlement_window == True`.
2. **For CASH trades**: each trade has `buy_client_identity` and `sell_client_identity`. Attribute the trade volume to BOTH sides:
   - Buy-side volume by participant type.
   - Sell-side volume by participant type.
3. Aggregate by `(symbol, trade_date, is_expiry, participant_type, side)`:
   - Total volume (shares), trade count.
   - % of total settlement window volume.
4. Also compute participant share for the **full day** (not just settlement window) as a baseline.

#### Output Metrics
| Metric | Definition |
|--------|-----------|
| `participant_share_settlement` | % of settlement window volume by participant type |
| `participant_share_fullday` | % of full day volume by participant type |
| `share_uplift` | `settlement_share - fullday_share` |
| `expiry_vs_control_delta` | Change in participant share from control day to expiry day |

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Chi-squared test** on volume distribution across participant types (expiry vs. control) | Test if participant mix changes on expiry |
| **Paired t-test** on Proprietary share (expiry vs. control) | Test H3 |
| **Paired t-test** on Custodian share (expiry vs. control) | Test H4 |

#### Charts
- **Stacked bar chart**: Volume by participant type, expiry vs. control, per symbol.
- **Grouped bar chart**: Participant share uplift (settlement vs. full day) by stock.
- **Heatmap**: Proprietary share by symbol × month on expiry days.

---

### Analysis A4 — `a4_algo_segmentation.py`: Algorithmic vs. Manual Trading

#### What We're Testing
**Hypothesis H5**: Algorithmic order flow increases disproportionately during the settlement window on expiry days.

**Hypothesis H6**: Algo orders on expiry days are more aggressive (higher IOC %, higher market order %) than algo orders on control days.

#### Algorithm
1. Load enriched CASH orders + FAO orders. Filter: `is_settlement_window == True`, `activity_type == 1` (new entries).
2. Segment by `algo_type` (Algo, Non-Algo, Algo-SOR, Non-Algo-SOR).
3. For each `(symbol, trade_date, is_expiry, algo_type)`:
   - Order count, total volume (`volume_original`).
   - IOC rate = count where `ioc_flag == 'Y'` / total.
   - Market order rate = count where `mkt_order_flag == 'Y'` / total.
4. From trades: segment trade volume by buy/sell algo indicators.
5. Compute `algo_share` = algo volume / total volume, for settlement window vs. full day.

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Paired t-test** on algo_share (expiry vs. control) | Test H5 |
| **Paired t-test** on algo_ioc_rate (expiry vs. control) | Test H6 |
| **Correlation**: algo_share vs. basis_std_dev (from A2) | Is more algo → more basis disruption? |

#### Charts
- **Stacked area chart**: Algo vs. Non-Algo volume, minute-by-minute, settlement window.
- **Scatter plot**: Algo share vs. basis volatility, colored by expiry/control.
- **Bar chart**: Algo IOC rate on expiry vs. control.

---

### Analysis A5 — `a5_cancellation_patterns.py`: Spoofing Detection

#### What We're Testing
**Hypothesis H7**: Cancel-to-entry ratios spike abnormally in the settlement window on expiry days, consistent with spoofing or layering strategies.

**Hypothesis H8**: Cancellation spikes are concentrated among Proprietary and Algo participants.

#### Algorithm
1. Load enriched CASH orders + FAO orders. Filter: `is_settlement_window == True`.
2. For each `(symbol, trade_date, is_expiry, time_bucket_1min)`:
   - Count `activity_type == 1` (entries), `== 3` (cancellations), `== 4` (modifications).
   - **Cancel-to-entry ratio** = cancellations / entries.
   - **Modification rate** = modifications / entries.
   - **Order lifespan proxy**: time between entry and cancel for same order_number.
3. Cross-tabulate by `participant_type` and `algo_type`.
4. Compare expiry vs. control.

#### Spoofing Flags
An order is flagged as **potential spoof** if:
- Entered and cancelled within < 1 second.
- Volume was large (> 2× median volume for that stock).
- Placed near top-of-book (within best 5 levels — requires CLOB from Stage 4).

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Paired t-test** on cancel_to_entry_ratio (expiry vs. control) | Test H7 |
| **Two-way ANOVA**: cancel_ratio ~ expiry_flag × participant_type | Test H8 (interaction) |
| **Fisher's exact test** on short-lived order counts (expiry vs. control) | More phantom orders on expiry? |

#### Charts
- **Heatmap**: Cancel-to-entry ratio by (symbol × minute), for each expiry day.
- **Line chart**: Cancel ratio minute-by-minute, expiry vs. control overlay.
- **Bar chart**: Cancel ratio by participant type, expiry vs. control.

---

### Analysis A6 — `a6_iceberg_detection.py`: Hidden Liquidity Analysis

#### What We're Testing
**Hypothesis H9**: Iceberg (disclosed quantity) orders are used more frequently during the settlement window on expiry days, masking true order size.

#### Algorithm
1. Load enriched CASH orders + FAO orders. Filter: `is_settlement_window == True`, `activity_type == 1`.
2. Identify icebergs: `volume_disclosed > 0 AND volume_disclosed < volume_original`.
3. For each `(symbol, trade_date, is_expiry)`:
   - **Iceberg ratio** = iceberg_count / total_entries.
   - **Hidden volume** = `sum(volume_original - volume_disclosed)` for icebergs.
   - **Hidden volume ratio** = hidden_volume / total_volume.
   - **Average disclosure ratio** = `mean(volume_disclosed / volume_original)` for icebergs.

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Paired t-test** on iceberg_ratio (expiry vs. control) | Test H9 |
| **Chi-squared**: iceberg usage by participant type on expiry days | Who uses icebergs more? |

#### Charts
- **Bar chart**: Iceberg ratio, expiry vs. control, by liquidity group.
- **Box plot**: Disclosure ratio distribution on expiry vs. control.

---

### Analysis A7 — `a7_ioc_aggressiveness.py`: Execution Urgency

#### What We're Testing
**Hypothesis H10**: IOC and market order usage spikes in the final minutes of the settlement window on expiry days.

**Hypothesis H11**: The spike accelerates non-linearly — the last 5 minutes (15:25–15:30) show disproportionately more aggressive orders than 15:00–15:25.

#### Algorithm
1. Load enriched CASH orders + FAO orders. Filter: `is_settlement_window == True`, `activity_type == 1`.
2. For each `(symbol, trade_date, is_expiry, time_bucket_1min)`:
   - **IOC ratio** = IOC_count / total_entries.
   - **Market order ratio** = market_count / total_entries.
   - **Aggressive order ratio** = (IOC + Market) / total.
3. Split into Early (15:00–15:24) and Late (15:25–15:30) sub-windows.

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Paired t-test** on IOC ratio (expiry vs. control) | Test H10 |
| **Paired t-test** on late_ioc_ratio - early_ioc_ratio (expiry vs. control) | Test H11 |
| **OLS regression**: ioc_ratio ~ minute × is_expiry (interaction) | Time-trend difference on expiry? |

#### Charts
- **Line chart**: IOC ratio minute-by-minute, expiry vs. control overlay.
- **Heatmap**: Aggressiveness ratio by (symbol × minute) for each expiry.

---

## STAGE 4: CLOB RECONSTRUCTION

### Why CLOB is Needed
Trade-level analysis (Stage 3) answers **what happened**. The CLOB answers **how orders impacted market structure** — spread widening, depth erosion, price impact. These are the mechanistic signatures of settlement manipulation.

### Task 4.1 — `stage4_clob/order_book.py`: OrderBook Class

```python
"""
OrderBook class using sortedcontainers for O(log n) price-level operations.

Internal state:
  - bid/ask: SortedDict mapping price → total qty at that level
  - orders: dict mapping order_number → {side, price, qty} for O(1) cancel/modify
"""
from sortedcontainers import SortedDict

class OrderBook:
    def __init__(self):
        self.bid = SortedDict()    # price → total_qty
        self.ask = SortedDict()    # price → total_qty
        self.orders = {}           # order_number → {"side", "price", "qty"}

    def process_event(self, order_number, activity_type, side, price, qty):
        """Process a single order event.
        activity_type: 1=Entry, 3=Cancel, 4=Modify
        side: "B" or "S"
        """
        if activity_type == 1:
            self._add_order(order_number, side, price, qty)
        elif activity_type == 3:
            self._cancel_order(order_number)
        elif activity_type == 4:
            self._cancel_order(order_number)
            self._add_order(order_number, side, price, qty)

    def _add_order(self, order_number, side, price, qty):
        book = self.bid if side == "B" else self.ask
        book[price] = book.get(price, 0) + qty
        self.orders[order_number] = {"side": side, "price": price, "qty": qty}

    def _cancel_order(self, order_number):
        if order_number not in self.orders:
            return
        info = self.orders.pop(order_number)
        book = self.bid if info["side"] == "B" else self.ask
        if info["price"] in book:
            book[info["price"]] -= info["qty"]
            if book[info["price"]] <= 0:
                del book[info["price"]]

    def remove_traded_qty(self, order_number, traded_qty):
        """Reduce qty for a partially filled order."""
        if order_number not in self.orders:
            return
        info = self.orders[order_number]
        book = self.bid if info["side"] == "B" else self.ask
        info["qty"] -= traded_qty
        if info["price"] in book:
            book[info["price"]] -= traded_qty
            if book[info["price"]] <= 0:
                del book[info["price"]]
        if info["qty"] <= 0:
            del self.orders[order_number]

    def snapshot(self, depth=10):
        """Return current book state: best N bid/ask levels."""
        best_bids = list(self.bid.items())[-depth:][::-1]  # highest first
        best_asks = list(self.ask.items())[:depth]          # lowest first

        best_bid_price = best_bids[0][0] if best_bids else None
        best_ask_price = best_asks[0][0] if best_asks else None
        midpoint = (best_bid_price + best_ask_price) / 2 if (best_bid_price and best_ask_price) else None
        spread = (best_ask_price - best_bid_price) if (best_bid_price and best_ask_price) else None

        return {
            "best_bid": best_bid_price,
            "best_ask": best_ask_price,
            "midpoint": midpoint,
            "spread": spread,
            "spread_bps": (spread / midpoint * 10000) if (spread and midpoint) else None,
            "bid_depth": [{"price": p, "qty": q} for p, q in best_bids],
            "ask_depth": [{"price": p, "qty": q} for p, q in best_asks],
            "total_bid_volume": sum(q for _, q in best_bids),
            "total_ask_volume": sum(q for _, q in best_asks),
        }
```

### Task 4.2 — `stage4_clob/clob_builder.py`: Replay Engine

**Purpose**: For one (symbol, date), replay all orders chronologically, build the book, emit snapshots every 1 second during settlement window + at every event during settlement window.

**Algorithm**:
1. Load enriched CASH orders for this (symbol, date) into Pandas. Sort by `txn_time_jiffies`.
2. Load enriched CASH trades (to remove filled qty from book).
3. Initialize empty `OrderBook`.
4. Iterate through every order event in timestamp order:
   - Call `book.process_event(...)`.
   - For trades at this timestamp, call `book.remove_traded_qty(...)`.
   - During 15:00–15:30: snapshot at every 1-second boundary AND at every order event.
5. Save snapshots as Parquet: `{CLOB_DATA_DIR}/{symbol}/date={date}/`

**Snapshot schema** (one row per snapshot):
| Column | Type | Description |
|--------|------|-------------|
| `symbol` | str | Stock symbol |
| `trade_date` | str | Date |
| `timestamp` | datetime | Exact time |
| `seconds_from_1500` | int | 0–1800 |
| `best_bid` | float | Best bid price |
| `best_ask` | float | Best ask price |
| `midpoint` | float | (bid + ask) / 2 |
| `spread` | float | ask - bid (rupees) |
| `spread_bps` | float | Spread in basis points |
| `bid_depth_1` … `bid_depth_10` | float | Volume at best 10 bid levels |
| `ask_depth_1` … `ask_depth_10` | float | Volume at best 10 ask levels |
| `total_bid_volume` | long | Sum of bid depth |
| `total_ask_volume` | long | Sum of ask depth |
| `book_imbalance` | float | `(bid - ask) / (bid + ask)` |
| `triggering_event` | str | "order_entry" / "order_cancel" / "order_modify" / "timer" |

### Task 4.3 — `stage4_clob/run_clob_all.py`: Parallel Orchestrator

```python
"""
Run CLOB for all (symbol, date) combos in parallel using multiprocessing.
"""
from multiprocessing import Pool
from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS, CLOB_PARALLEL_WORKERS

def build_one(args):
    symbol, date = args
    # load data, run clob_builder, save snapshots

if __name__ == "__main__":
    tasks = [(s, d) for s in TARGET_SYMBOLS for d in ALL_TARGET_DATES]
    with Pool(CLOB_PARALLEL_WORKERS) as pool:
        pool.map(build_one, tasks)
```

---

## STAGE 5: CLOB-BASED ANALYSIS (5 Modules)

---

### Analysis B1 — `b1_spread_dynamics.py`: Bid-Ask Spread Evolution

#### Hypotheses
**H12**: Bid-ask spread widens significantly during settlement window on expiry days vs. control days.
**H13**: Spread widening is more severe for illiquid stocks.

#### Output Metrics
| Metric | Definition |
|--------|-----------|
| `mean_spread_bps` | Avg spread in bps during settlement window |
| `max_spread_bps` | Maximum spread during settlement window |
| `spread_jump_at_1500` | Spread at 15:01 minus spread at 14:59 |
| `spread_expansion_ratio` | Settlement mean spread / pre-settlement mean spread |

#### Statistical Tests
- **Paired t-test** on mean_spread_bps (expiry vs. control) → H12
- **Two-sample t-test**: liquid vs. illiquid spread_expansion_ratio → H13

---

### Analysis B2 — `b2_depth_erosion.py`: Order Book Depth

#### Hypotheses
**H14**: Depth at best price levels decreases during settlement window on expiry days.
**H15**: Depth erosion is asymmetric — one side loses more, suggesting directional pressure.

#### Output Metrics
| Metric | Definition |
|--------|-----------|
| `depth_erosion_ratio` | Settlement avg depth / pre-settlement avg depth |
| `avg_book_imbalance` | Mean (bid - ask) / (bid + ask) during settlement |
| `max_abs_imbalance` | Peak imbalance magnitude |
| `imbalance_direction` | Sign of avg imbalance (+1 = bid-heavy, -1 = ask-heavy) |

#### Statistical Tests
- **Paired t-test** on depth_erosion_ratio → H14
- **One-sample t-test** on avg_book_imbalance on expiry days (≠ 0?) → H15
- **Correlation**: book_imbalance vs. VWAP direction → mechanism validation

---

### Analysis B3 — `b3_order_flow_imbalance.py`: Net Order Pressure

#### Hypothesis
**H16**: Net order flow is significantly more one-sided during settlement window on expiry days.

#### Output Metrics
| Metric | Definition |
|--------|-----------|
| `cash_ofi` | Cash order flow imbalance (volume-weighted) |
| `futures_ofi` | Futures OFI |
| `cross_market_signal` | "arbitrage" if opposite sign, "directional" if same |

#### Statistical Tests
- **Paired t-test** on |cash_ofi| → H16
- **Granger causality**: futures_ofi → cash_ofi or vice versa → who moves first?

---

### Analysis B4 — `b4_price_impact.py`: Per-Trade Impact

#### Hypothesis
**H17**: Per-trade price impact (midpoint displacement per unit volume) is larger during settlement window on expiry days.

#### Statistical Tests
- **Paired t-test** on median normalized impact → H17
- **Regression**: impact ~ log(trade_size) × is_expiry → steeper on expiry?

---

### Analysis B5 — `b5_book_asymmetry.py`: Directional Book Pressure

#### Hypotheses
**H18**: Order book exhibits sustained asymmetry during settlement window on expiry days.
**H19**: Book asymmetry direction predicts VWAP drift direction.

#### Output Metrics
| Metric | Definition |
|--------|-----------|
| `log_book_pressure` | ln(bid_volume / ask_volume) |
| `book_pressure_persistence` | % of seconds with same-sign imbalance |
| `book_pressure_trend` | OLS slope of log_pressure vs. time |

#### Statistical Tests
- **Paired t-test** on book_pressure_persistence → H18
- **Correlation**: mean_log_pressure vs. VWAP terminal drift → H19
- **Logistic regression**: predict VWAP direction from early (15:00–15:10) book pressure → can early state predict final VWAP?

---

## STAGE 6: BLOOMBERG-INTEGRATED ANALYSIS (3 Modules)

### Conceptual Framework

```
                 BLOOMBERG DATA                        NSE MICROSTRUCTURE
                 ──────────────                        ──────────────────
    Calendar Spread narrowing → Long rolls dominate    VWAP drift direction
    OI migrating near → far   → Confirming roll        Book asymmetry direction
    Basis compressing          → Selling near-month     Order flow imbalance
                                                       Participant profile
                      │                                        │
                      └──────────┬─────────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  DIRECTIONAL VALIDATION │
                    │  Do they agree?         │
                    │  If yes → settlement    │
                    │  punching aligned with  │
                    │  roll pressure          │
                    └─────────────────────────┘
```

**Key insight**: If rolls are predominantly long (participants closing long near-month, opening long far-month), then near-month futures face **selling pressure**. To settle at a favorable VWAP, these participants would want the cash VWAP pushed **down**. If we observe downward VWAP drift + bid-side depth erosion + sell-heavy order flow during settlement on the same expiry, that's **directionally consistent** with roll-driven settlement punching.

---

### Analysis C1 — `c1_roll_pressure.py`: Long/Short Roll Direction

#### What We're Computing

For each `(symbol, expiry_month)`, determine whether roll pressure was predominantly **long** (net long positions being rolled → sell near, buy far) or **short** (net short positions being rolled → buy near, sell far).

#### Algorithm
1. Load Bloomberg calendar spread and OI data.
2. For each symbol, look at the **5 trading days before expiry** (the "roll window"):

   **Signal 1 — Calendar Spread Compression/Expansion**:
   - If `calendar_spread` (near - far) is **declining** (narrowing or going more negative) → near-month is weakening relative to far → consistent with **long rolls** (selling near, buying far).
   - If `calendar_spread` is **rising** → near-month strengthening → consistent with **short rolls**.
   - Compute: `spread_change_5d = spread[expiry-1] - spread[expiry-5]`.

   **Signal 2 — OI Migration**:
   - `oi_migration_rate = Δ(far_month_oi) / |Δ(near_month_oi)|` over 5 days.
   - If near_month_oi is declining AND far_month_oi is increasing → rolls happening.
   - The **net** of near-month OI change tells direction: large near-month OI decline that exceeds far-month OI increase → some positions are closing outright (not rolling).

   **Signal 3 — Volume Ratio**:
   - `roll_activity_ratio = far_month_volume / near_month_volume` on the day before expiry.
   - High ratio = active rolling.

   **Signal 4 — Basis Behavior**:
   - If near-month basis (futures - spot) is **declining** into expiry → selling pressure on near futures → **long rolls**.
   - If near-month basis is **rising** → buying pressure → **short rolls**.
   - Compute: `basis_drift_5d = basis[expiry-1] - basis[expiry-5]`.

3. **Combine signals** into a composite roll direction score:
   ```
   roll_direction_score = weighted_average(
       spread_change_signal,      # -1 if declining (long roll), +1 if rising (short roll)
       oi_migration_signal,       # based on asymmetry of OI migration
       basis_drift_signal         # -1 if declining, +1 if rising
   )
   ```
   - Score < 0 → **Long rolls dominate** (sell near, buy far) → settlement punch direction = DOWN
   - Score > 0 → **Short rolls dominate** (buy near, sell far) → settlement punch direction = UP

#### Output
| Column | Description |
|--------|-------------|
| `symbol` | Stock |
| `expiry_date` | Expiry Thursday |
| `spread_change_5d` | Calendar spread change over 5 days |
| `oi_migration_rate` | OI migration ratio |
| `basis_drift_5d` | Basis change over 5 days |
| `roll_direction_score` | Composite score (negative = long roll, positive = short roll) |
| `predicted_punch_direction` | "DOWN" if long roll, "UP" if short roll |
| `roll_intensity` | abs(roll_direction_score) — how strong is the signal? |

---

### Analysis C2 — `c2_cost_of_carry.py`: Fair Value Basis & Mispricing

#### What We're Computing

Compare the actual observed basis against the **theoretical fair basis** (based on risk-free rate and days to expiry). The difference = mispricing. If mispricing increases during settlement, it suggests the VWAP is being distorted away from fair value.

#### Algorithm
1. Load Bloomberg cost-of-carry data.
2. For each `(symbol, date)`:
   - **Theoretical fair basis** = `spot_price × risk_free_rate × (days_to_expiry / 365)`.
   - **Actual basis** = `futures_close - spot_close`.
   - **Mispricing** = `actual_basis - theoretical_basis` (in rupees and bps).
3. Track mispricing evolution over the last 5 days before expiry.
4. Compare the **settlement VWAP** (from A1) against the closing spot price to see if settlement pricing deviates from end-of-day fair value.

#### Output
| Column | Description |
|--------|-------------|
| `theoretical_basis_pct` | Fair basis as % of spot |
| `actual_basis_pct` | Actual basis as % of spot |
| `mispricing_bps` | (actual - theoretical) in basis points |
| `mispricing_trend` | Is mispricing growing or shrinking into expiry? |

---

### Analysis C3 — `c3_directional_validation.py`: Cross-Referencing Roll Direction with NSE Microstructure

#### What We're Testing

**Hypothesis H20**: The direction of VWAP drift during the settlement window is consistent with Bloomberg-derived roll pressure direction — i.e., if long rolls dominate, VWAP drifts downward.

**Hypothesis H21**: The magnitude of VWAP distortion is correlated with roll intensity — more intense roll pressure → larger VWAP drift.

**Hypothesis H22**: Order book asymmetry direction (from B5) aligns with roll direction — if long rolls dominate, the book should be ask-heavy (more sell pressure) during settlement.

**Hypothesis H23**: Basis mispricing at settlement is larger on expiry days where roll intensity is high.

#### Algorithm
1. Load C1 output (roll direction per symbol per expiry).
2. Load A1 output (VWAP trajectory — compute terminal drift direction).
3. Load B5 output (book asymmetry direction).
4. Load B3 output (order flow imbalance direction).
5. For each `(symbol, expiry_date)`:

   **Validation 1 — VWAP Drift vs. Roll Direction**:
   - `vwap_drift` = VWAP at 15:30 minus VWAP at 15:00 (or vs. pre-settlement LTP).
   - `drift_direction` = "DOWN" if negative, "UP" if positive.
   - **Match** = 1 if `drift_direction == predicted_punch_direction`, 0 otherwise.
   - Under null (random), match rate should be ~50%. If significantly > 50%, roll direction predicts settlement behavior.

   **Validation 2 — Book Asymmetry vs. Roll Direction**:
   - If long rolls → expected ask-heavy book (book_imbalance < 0).
   - If short rolls → expected bid-heavy book (book_imbalance > 0).
   - **Match** = 1 if directions align.

   **Validation 3 — OFI vs. Roll Direction**:
   - If long rolls → expected net sell OFI (cash_ofi < 0).
   - If short rolls → expected net buy OFI (cash_ofi > 0).

6. Compute match rates across all 120 symbol-expiry observations (10 × 12).

#### Statistical Tests
| Test | Purpose |
|------|---------|
| **Binomial test**: is match rate significantly > 50%? | Test H20 (VWAP direction) |
| **Spearman correlation**: roll_intensity vs. abs(vwap_drift) | Test H21 (magnitude) |
| **Binomial test**: book asymmetry direction match rate | Test H22 |
| **Regression**: abs(mispricing_bps) ~ roll_intensity × is_expiry | Test H23 |

#### Charts
- **Confusion matrix / contingency table**: Roll direction vs. VWAP drift direction.
- **Scatter plot**: Roll intensity vs. VWAP drift magnitude, colored by match/mismatch.
- **Panel chart**: For each expiry month, show roll direction arrows alongside VWAP trajectory and book imbalance.
- **Summary dashboard**: All 3 validation signals (VWAP, book, OFI) aligned vs. misaligned per symbol-expiry.

---

## STAGE 7: CONSOLIDATED REPORT

### Task 7.1 — `stage7_report/stat_tests.py`

Run ALL hypothesis tests, output a summary table:

| Hypothesis | Test | Statistic | p-value | Effect Size | Conclusion |
|-----------|------|-----------|---------|-------------|------------|
| H1: Basis vol ↑ on expiry | Paired t | t = ... | p = ... | d = ... | ... |
| ... | ... | ... | ... | ... | ... |
| H23: Mispricing ~ roll intensity | Regression | β = ... | p = ... | R² = ... | ... |

Significance level α = 0.05. **Bonferroni correction** for 23 tests → α_adj = 0.05/23 = 0.0022.

### Task 7.2 — `stage7_report/generate_charts.py`

Publication-quality charts:
- Figure size: 10×6 inches, serif font, 12pt
- Both PNG (300 DPI) and PDF
- Color scheme: blue = expiry, gray = control, red/green for bid/ask, orange = Bloomberg signal

### Task 7.3 — `stage7_report/generate_report.py`

Final report with:
- Executive summary
- Methodology (NSE data + Bloomberg data sources)
- Results per hypothesis
- Bloomberg cross-validation section
- Charts embedded
- Data quality notes
- Limitations and future work

---

## MASTER PIPELINE — `main.py`

```python
"""
Usage:
  python main.py --stage parse              # Stage 1
  python main.py --stage enrich             # Stage 2
  python main.py --stage analyze            # Stage 3 (trade-level)
  python main.py --stage clob               # Stage 4 (CLOB build)
  python main.py --stage clob-analyze       # Stage 5 (CLOB analysis)
  python main.py --stage bloomberg          # Stage 6 (Bloomberg integration)
  python main.py --stage report             # Stage 7 (consolidated report)
  python main.py --stage all                # Everything end-to-end
  python main.py --stage parse --date 27012022  # Single date
"""
```

---

## Time Estimates

| Stage | Estimated Time | Notes |
|-------|---------------|-------|
| Stage 0B: Bloomberg data pull | 1–2 hrs (manual) | Pull from terminal, export CSVs |
| Stage 1: Parse (24 days × 4 files) | 12–22 hrs | Run overnight in batches |
| Stage 2: Enrich | 30–60 min | Parquet → Parquet |
| Stage 3: Trade-level analysis (7 modules) | 30–60 min | Aggregations |
| Stage 4: CLOB reconstruction | 2.5–4 hrs | 6 parallel workers |
| Stage 5: CLOB analysis (5 modules) | 30–60 min | Aggregations |
| Stage 6: Bloomberg analysis (3 modules) | 15–30 min | Small data, Pandas |
| Stage 7: Report generation | 10–20 min | Stats + charts |
| **Total** | **~18–30 hrs** | Parse dominates |

**Practical schedule**: Pull Bloomberg data on day 1. Parse NSE over 3 nights. Run Stages 2–7 in a single afternoon.

---

## Summary of All 23 Hypotheses

| # | Hypothesis | Source | Module |
|---|-----------|--------|--------|
| H1 | Basis volatility is higher on expiry days | NSE | A2 |
| H2 | Illiquid stocks show more basis divergence | NSE | A2 |
| H3 | Proprietary desks increase share on expiry | NSE | A3 |
| H4 | Custodian activity patterns change on expiry | NSE | A3 |
| H5 | Algo order flow increases on expiry | NSE | A4 |
| H6 | Algo orders are more aggressive on expiry | NSE | A4 |
| H7 | Cancel-to-entry ratios spike on expiry | NSE | A5 |
| H8 | Cancellation spikes come from Prop + Algo | NSE | A5 |
| H9 | Iceberg orders increase on expiry | NSE | A6 |
| H10 | IOC/market order usage spikes on expiry | NSE | A7 |
| H11 | Aggressiveness accelerates in final 5 min | NSE | A7 |
| H12 | Bid-ask spread widens on expiry | NSE | B1 |
| H13 | Spread widening worse for illiquid stocks | NSE | B1 |
| H14 | Book depth decreases on expiry | NSE | B2 |
| H15 | Depth erosion is asymmetric (directional) | NSE | B2 |
| H16 | Order flow is more one-sided on expiry | NSE | B3 |
| H17 | Per-trade price impact is larger on expiry | NSE | B4 |
| H18 | Book asymmetry is persistent on expiry | NSE | B5 |
| H19 | Book pressure predicts VWAP drift direction | NSE | B5 |
| H20 | VWAP drift direction matches roll pressure | BBG+NSE | C3 |
| H21 | VWAP drift magnitude correlates with roll intensity | BBG+NSE | C3 |
| H22 | Book asymmetry aligns with roll direction | BBG+NSE | C3 |
| H23 | Basis mispricing is larger when roll intensity is high | BBG+NSE | C3 |
