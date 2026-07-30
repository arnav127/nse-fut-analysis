# Expiry Day Dynamics & VWAP Settlement Anomalies

Empirical market microstructure analysis pipeline for NSE tick-level order/trade data and Bloomberg Terminal roll/spread metrics.

Designed and optimized for **single-machine execution** (i7 8th Gen, 24 GB RAM, Windows) using PySpark local mode, PyArrow, and a high-performance C++/Numba Limit Order Book engine.

---

## Directory Structure

```
ProjectCourse/
├── config/
│   ├── settings.py              # Constants, paths, target symbols, dates, Spark config
│   └── schema_definitions.py    # Fixed-width record layouts for CM/FAO Orders & Trades
├── utils/
│   ├── spark_session.py         # Local PySpark session builder
│   ├── jiffies_converter.py     # Jiffies (65536/sec) to Datetime conversion
│   └── price_converter.py       # Paise to Rupees conversion
├── stage1_parse/
│   ├── parse_cash_orders.py     # Parse CASH_Orders_DDMMYYYY.DAT.gz -> Parquet
│   ├── parse_cash_trades.py     # Parse CASH_Trades_DDMMYYYY.DAT.gz -> Parquet
│   ├── parse_fao_orders.py      # Parse FAO_Orders_DDMMYYYY_nn.DAT.gz -> Parquet
│   ├── parse_fao_trades.py      # Parse FAO_Trades_DDMMYYYY_nn.DAT.gz -> Parquet
│   └── run_parse_all.py         # Stage 1 orchestrator
├── stage2_enrich/
│   ├── enrich_cash.py           # Add datetime, rupee prices, flags, labels to CASH
│   ├── enrich_fao.py            # Add datetime, rupee prices, flags, labels to FAO
│   └── run_enrich_all.py        # Stage 2 orchestrator
├── stage3_analysis/
│   ├── a1_vwap_trajectory.py    # Minute-by-minute cumulative VWAP & basis trajectory
│   ├── a2_basis_divergence.py   # Basis volatility & divergence stats (H1, H2)
│   ├── a3_participant_profile.py# Participant segmentation: Custodian, Prop, NCNP (H3, H4)
│   ├── a4_algo_segmentation.py  # Algo vs Non-Algo order flow & aggressiveness (H5, H6)
│   ├── a5_cancellation_patterns.py# Cancel-to-entry ratios & spoofing signals (H7, H8)
│   ├── a6_iceberg_detection.py  # Disclosed quantity & hidden volume analysis (H9)
│   ├── a7_ioc_aggressiveness.py # IOC & Market order urgency (H10, H11)
│   └── run_all_analysis.py      # Stage 3 orchestrator
├── stage4_clob/
│   ├── order_book.py            # Limit Order Book class (auto C++ PyBind11 / Numba fallback)
│   ├── clob_builder.py          # Chronological order event replay & 1s snapshot engine
│   ├── clob_schemas.py          # Snapshot schema definitions
│   ├── run_clob_all.py          # Multiprocessing parallel CLOB runner
│   └── cpp/
│       ├── order_book_cpp.cpp   # C++ OrderBook PyBind11 engine source
│       ├── setup.py             # MSVC & MinGW build script
│       └── build_mingw.py       # Standalone MinGW (g++) compiler helper
├── stage5_clob_analysis/
│   ├── b1_spread_dynamics.py    # Bid-Ask spread dynamics & expansion (H12, H13)
│   ├── b2_depth_erosion.py      # Order book depth & asymmetric erosion (H14, H15)
│   ├── b3_order_flow_imbalance.py# Order Flow Imbalance (OFI) (H16)
│   ├── b4_price_impact.py       # Per-trade price impact (H17)
│   ├── b5_book_asymmetry.py     # Directional book pressure & persistence (H18, H19)
│   └── run_clob_analysis.py     # Stage 5 orchestrator
├── stage6_bloomberg/
│   ├── bloomberg_data_guide.md  # Terminal export guide
│   ├── load_bloomberg_data.py   # Bloomberg CSV loader
│   ├── c1_roll_pressure.py      # Long/Short roll direction classification
│   ├── c2_cost_of_carry.py      # Theoretical fair basis & mispricing (H23)
│   ├── c3_directional_validation.py# Cross-referencing roll pressure vs VWAP drift (H20-H22)
│   └── run_bloomberg_analysis.py# Stage 6 orchestrator
├── stage7_report/
│   ├── stat_tests.py            # Consolidated hypothesis testing engine (H1-H23)
│   ├── generate_charts.py       # Publication-quality figure generation
│   └── generate_report.py       # Final markdown research report compiler
├── data/
│   ├── raw/                     # Place raw .DAT.gz files here
│   ├── parsed/                  # Stage 1 Parquet outputs
│   ├── enriched/                # Stage 2 Parquet outputs
│   ├── clob_snapshots/          # Stage 4 CLOB snapshot Parquets
│   ├── bloomberg/               # Exported Bloomberg CSVs
│   └── results/                 # Analysis CSV outputs, PNG figures, and final report
├── main.py                      # Master pipeline entrypoint
├── requirements.txt             # Dependencies
└── README.md
```

---

## Quick Start

### 1. Requirements & Setup

Install dependencies:
```bash
pip install -r requirements.txt
```

#### *(Optional)* Compile C++ OrderBook Extension for Ultra-Fast Reconstruction

If using **MinGW (`g++`)**:
```bash
python stage4_clob/cpp/build_mingw.py
```
Or:
```bash
python stage4_clob/cpp/setup.py build_ext --compiler=mingw32 --inplace
```

If using **MSVC (Visual Studio Build Tools)**:
```bash
python stage4_clob/cpp/setup.py build_ext --inplace
```

*(If uncompiled, the pipeline automatically falls back to the fast Python/Numba engine).*

---

### 2. Execution Options

Run the full pipeline end-to-end on your machine:
```bash
python main.py --stage all
```

Or run stage-by-stage:
```bash
python main.py --stage parse        # Stage 1: Parse fixed-width .DAT.gz files to Parquet
python main.py --stage enrich       # Stage 2: Add timestamps, prices, flags, labels
python main.py --stage analyze      # Stage 3: Trade-level analysis (H1-H11)
python main.py --stage clob         # Stage 4: Replay CLOB & take 1s snapshots
python main.py --stage clob-analyze # Stage 5: CLOB-based microstructure analysis (H12-H19)
python main.py --stage bloomberg    # Stage 6: Bloomberg roll pressure integration (H20-H23)
python main.py --stage report       # Stage 7: Run hypothesis tests & generate report + charts
```
