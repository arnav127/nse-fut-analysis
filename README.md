# What Happens in the Last Half Hour? Expiry days and the settlement VWAP on the NSE

Code for the IIM Ahmedabad project course report by Arnav Dixit (PGPGC202500112) and Mayank
Gomekar (PGPGC202500150), supervised by Prof. Anirban Banerjee.

The project uses the National Stock Exchange's order and trade files for 2022 to study the
settlement window (15:00 to 15:30) on derivatives expiry days: whether settlement prices are
pushed, whether the window costs more to trade in, whether order flow is one-sided, how order
behaviour changes, and why.

The NSE files are licensed and are **not** in this repository. Everything here runs from them.

## Where each part of the report comes from

| Report section | Code |
|---|---|
| Decoding the raw NSE files | [`stage1_parse/`](stage1_parse), using our parser [nsetick](https://github.com/arnav127/nsetick) |
| Choosing the liquid, illiquid and placebo stocks | [`scripts/build_universe.py`](scripts/build_universe.py), [`scripts/fo_from_tape.py`](scripts/fo_from_tape.py), [`config/universe.py`](config/universe.py) |
| Placebo stocks: Nifty 500 membership and turnover rank | [`stage9_tape/placebo_check.py`](stage9_tape/placebo_check.py), [`scripts/cash_cross_section.py`](scripts/cash_cross_section.py) |
| Rebuilding the order book | [`stage4_clob/`](stage4_clob) |
| Order book measures in the window | [`stage5_clob_analysis/`](stage5_clob_analysis), [`stage6_insights/`](stage6_insights) (s1 to s6) |
| The four broad hypotheses and their paired tests | [`stage8_report/stat_tests.py`](stage8_report/stat_tests.py) |
| Full-year daily data, window share, reversal, order imbalance, flows | [`stage9_tape/daily_tape.py`](stage9_tape/daily_tape.py), [`stage9_tape/settlement_tests.py`](stage9_tape/settlement_tests.py), [`stage9_tape/calendar.py`](stage9_tape/calendar.py) |
| Fixed-effects regressions | [`utils/panel.py`](utils/panel.py) |
| Is the next-morning fall news? | [`stage9_tape/overnight_tests.py`](stage9_tape/overnight_tests.py) |
| The index (Nifty 50 vs Nifty Next 50) | [`stage9_tape/index_tests.py`](stage9_tape/index_tests.py) |
| Is the index fall hedge unwinding? (open interest, positions, flows) | [`stage9_tape/hedge_tests.py`](stage9_tape/hedge_tests.py), [`stage9_tape/index_deriv_trades.py`](stage9_tape/index_deriv_trades.py) |
| Spread and depth through the day, the volatility explanation | [`stage9_tape/book_profile.py`](stage9_tape/book_profile.py), [`stage9_tape/followups.py`](stage9_tape/followups.py) |
| BH2 panel with stock fixed effects | [`stage9_tape/bh2_panel.py`](stage9_tape/bh2_panel.py) |
| Futures pricing and strike pinning | [`stage6_insights/s7_futures_convergence.py`](stage6_insights/s7_futures_convergence.py), [`stage6_insights/s8_strike_pinning.py`](stage6_insights/s8_strike_pinning.py) |
| Futures trades and futures order books | [`stage9_tape/futures_tape.py`](stage9_tape/futures_tape.py), [`stage9_tape/futures_book.py`](stage9_tape/futures_book.py), [`scripts/fao_links.py`](scripts/fao_links.py) |
| Report and its charts | [`report/report.tex`](report/report.tex), [`report/make_figures.py`](report/make_figures.py) |
| Longer technical write-up with every table | [`paper/`](paper), built by [`stage8_report/`](stage8_report) |

## Data

| Data | Source | In this repository |
|---|---|---|
| Cash market order and trade files, 2022 (`CASH_Orders_*`, `CASH_Trades_*`) | NSE historical data (licensed) | No |
| Index file, Nifty 50 and Nifty Next 50 every second (`CASH_Index_*`) | NSE historical data (licensed) | No |
| F&O order and trade files, 2022 (`FAO_Orders_*`, `FAO_Trades_*`) | NSE historical data (licensed) | No |
| Daily F&O bhavcopy (open interest by contract) | [NSE archives](https://archives.nseindia.com/content/historical/DERIVATIVES/) | No (public; downloaded by date) |
| Participant-wise open interest | [NSE archives](https://archives.nseindia.com/content/nsccl/) (`fao_participant_oi_DDMMYYYY.csv`) | No (public) |
| Nifty 50 and Nifty 500 constituents | NSE constituent files, archived copies of July and October 2022 | No |
| F&O underlyings and the selected universe | derived from the trade files | [`config/`](config) |

## Running it

Install the parser ([nsetick on PyPI](https://pypi.org/project/nsetick/)) and the Python packages:

```bash
pip install nsetick
pip install -r requirements.txt
```

Put the raw files in one folder and point the pipeline at it:

```bash
export NSE_RAW_DIR=/path/to/nse/files      # the .DAT.gz files as NSE ships them
export NSE_DATA_DIR=/path/to/working/data  # parsed data and results go here
python run_all.py --jobs 4                 # parse, rebuild books, all analyses, report
```

Each stage checks for its own output first, so an interrupted run resumes. Single stages run
with `python run_all.py --stage <name>` (see `--help`). The later analyses run as modules:

```bash
python -m stage9_tape.overnight_tests      # news test
python -m stage9_tape.book_profile         # spread and depth through the day
python -m stage9_tape.followups            # volatility explanation, futures figures
python -m stage9_tape.bh2_panel            # BH2 panel regressions
python -m stage9_tape.futures_tape         # futures trades
python -m stage9_tape.futures_book         # futures order books
python -m stage9_tape.index_deriv_trades   # Nifty futures and options trades
python -m stage9_tape.placebo_check        # placebo stocks in the market
python -m stage9_tape.hedge_tests          # open interest and hedge tests
python report/make_figures.py              # charts for the report
```

The parsing and order book steps need the raw files and a multi-core machine. Everything after
the daily tables run on a laptop. Tests: `python -m pytest tests -q`.
