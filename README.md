# Expiry Day Dynamics & VWAP Settlement Anomalies

Market microstructure analysis of NSE expiry Thursdays against matched control days, built
from Level 3 order-by-order tick data and Bloomberg roll/basis metrics.

Twelve expiry sessions and twelve controls from 2022, ten equities split into a liquid and
an illiquid group, and thirty hypotheses about what happens to the book between 15:00 and
15:30 when the futures settlement VWAP is being set.

---

## Requirements

Parsing and order book reconstruction are done by [nsetick](https://github.com/arnav127/nsetick),
a Rust library that reads the NSE fixed-width feeds. It is not on PyPI; build the wheel from
the sibling checkout and install it:

```bash
cd ../nsetick && maturin build --release -m crates/nsetick-py/Cargo.toml
pip install ../nsetick/target/wheels/nsetick-*.whl
```

Then the rest:

```bash
pip install -r requirements.txt
```

Raw `.DAT.gz` files go in `data/raw/`, named as NSE ships them
(`CASH_Orders_27012022.DAT.gz`, `FAO_Trades_27012022_01.DAT.gz`, and so on).

## Running it

```bash
python run_all.py
```

That is the whole pipeline. Stages 1, 2 and 4 check for their own output before doing
anything, so an interrupted run resumes where it stopped rather than starting over.

```bash
python run_all.py --stage parse          # one stage; see --help for the list
python run_all.py --date 27012022        # one session through the data stages
python run_all.py --force                # redo work already on disk
python run_all.py --parse-all-eq         # keep every EQ symbol, not just the ten studied
```

Logs are written per stage under `logs/`, results to `data/results/`.

```bash
python -m pytest tests -q          # 47 tests over the analysis and macro layers
```

---

## Stages

| | Stage | Reads | Writes |
|---|---|---|---|
| 1 | Parse | `data/raw/*.DAT.gz` | `data/parsed/<feed>/date=<session>/symbol=*/` |
| 2 | Enrich | parsed | `data/enriched/<feed>/date=<session>/sym=*/` |
| 3 | Trade analysis (A1–A12) | enriched | `data/results/a*.csv` |
| 4 | Book reconstruction | parsed orders | `data/clob_books/`, `data/clob_snapshots/` |
| 5 | Book analysis (B1–B7) | snapshots, enriched | `data/results/b*.csv` |
| 6 | Bloomberg (C1–C4) | `data/bloomberg/*.csv` | `data/results/c*.csv` |
| 7 | Report | all results | `data/results/final_research_paper.{md,tex,pdf}` |

### Stage 1 — parse

`nsetick.parse` decodes each feed against its versioned layout, selecting the record version
by date and validating it against the observed record length. Symbol padding is stripped,
prices are kept as integer paise, and jiffies become real timestamps, all in the single
decode pass. Output is one directory per feed, partitioned by symbol.

Narrowed to `TARGET_SYMBOLS`. Decoding costs the same either way - every record is read
regardless and the symbol filter is a bucketed set lookup - but the output does not: a
session carries roughly 1,900 EQ symbols and the study uses ten. `--parse-all-eq` keeps
them all, at roughly two orders of magnitude more Parquet.

### Stage 2 — enrich

Turns exchange codes into the variables the hypotheses are written in - participant class,
algo class, activity kind - converts paise to rupees, and stamps each row with its session,
window and expiry flag. Narrowed to `TARGET_SYMBOLS`, one session at a time.

Every row carries both date spellings: `session` (`27012022`, the NSE file's own name, which
the expiry calendar uses) and `trade_date` (ISO, derived from the timestamp).

### Stage 4 — book reconstruction

`nsetick.build_books` replays the parsed order events into a per-symbol limit order book and
snapshots it every second at 20 levels, honouring disclosed-quantity replenishment and the
queue-priority loss it entails. The settlement-window slice is flattened into
`data/clob_snapshots/` with the column names the stage-5 analyses read, including hidden
size at every level.

### Stage 6 - settlement-window analysis

The measures that make the study more than a description of a busy half hour.

`s1` computes the settlement VWAP itself and places it against the mid at the window's open,
the closing price and the final minute's own average. `s2` separates directional pressure
from heavier two-sided trading: a variance ratio, the persistence of signed order flow, and
the share of price impact that survives a minute all respond to the two explanations with
opposite signs. `s3` measures concealed size and how fast it is replenished. `s4` sweeps the
displayed book by a fixed notional and records how far the price moves, which is the cost of
marking the settlement. `s5` builds the minute-by-minute profile behind the figures. `s6`
runs the two differences-in-differences: derivatives securities against the placebo group,
and illiquid against liquid.

### Stage 8 - the report

The manuscript is LaTeX source under `paper/`, edited directly as LaTeX. The pipeline never
writes prose. It writes only what it computes:

```
paper/main.tex           the document; edit this
paper/sections/*.tex     the prose; edit these
paper/generated/         macros, provenance and tables - overwritten every run
paper/figures/           plots - overwritten every run
```

No number is typed into the prose. Each quantity is recorded by the code that computes it,
with its unit and a note, and cited as `\MacroName{}`. `audit_macros.py` runs before the
compile and fails the build in either direction: on a quantity the text cites but nothing
computed, and on a numeral appearing in the authored text. The first is defined as a visible
`??` so the document still builds and the gap shows on the page.

To add a number: record it in `collect_metrics.py` or `collect_insights.py`, then cite it.
Macro names follow the recorded key with digits spelled out, since LaTeX command names cannot
contain them - `s2.p_value` becomes `\STwoPValue`.

Sample counts come from nsetick's parse manifests rather than from the configuration, so the
report states what was actually read.

---

## Where the byte layouts live

In nsetick, under `spec/layouts/*.toml`, and nowhere else. This repository used to carry a
second transcription of the NSE offsets in `config/schema_definitions.py`, and its git
history is five consecutive commits repairing a symbol offset that had drifted from the
specification - each of which produced output that looked entirely valid. Deleting the
second copy is what makes that class of bug impossible rather than merely unlikely.

## Layout

```
config/
  settings.py          paths, universe, session calendar, window and book parameters
  categories.py        the four feeds and their nsetick layouts and filters
utils/
  paths.py             layer paths and the session/ISO date conversions
  logger.py            per-stage file and console logging
  progress.py          progress display for the long Rust calls
stage1_parse/          tick_parser.py, run_parse_all.py
stage2_enrich/         enricher.py, run_enrich_all.py
stage3_analysis/       a1..a12 plus run_all_analysis.py
stage4_clob/           clob_builder.py, run_clob_all.py
stage5_clob_analysis/  b1..b7 plus run_clob_analysis.py
stage6_bloomberg/      c1..c4, load_bloomberg_data.py, run_bloomberg_analysis.py
stage7_report/         stat_tests.py, generate_charts.py, generate_report.py
run_all.py             entry point
```
