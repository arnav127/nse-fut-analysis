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
./run.sh
```

Edit the `SETTINGS` block at the top of `run.sh` - where the raw files are, where the output
goes, how many sessions at once - and run it. It checks its prerequisites, builds the
universe if that has not been done, runs the pipeline and compiles the report, logging to
`logs/run-<timestamp>.log`.

Anything already in the environment wins over the settings in the file, so a one-off change
needs no edit: `JOBS=8 ./run.sh`. Arguments are forwarded to the pipeline, so
`./run.sh --stage report` does one stage. On a SLURM cluster the same file submits as a job:
`sbatch run.sh`.

The steps underneath, if you would rather drive them yourself:

```bash
python run_all.py
```

That is the whole pipeline. Stages 1, 2 and 4 check for their own output before doing
anything, so an interrupted run resumes where it stopped rather than starting over.

```bash
python run_all.py --stage parse          # one stage; see --help for the list
python run_all.py --date 27012022        # one session through the data stages
python run_all.py --force                # redo work already on disk
python run_all.py --jobs 4               # four sessions at a time
```

Logs are written per stage under `logs/`, results to `data/results/`.

### Running on a cluster

```bash
export NSE_RAW_DIR=/shared/nse/raw                # sequential reads of large .gz - network is fine
export NSE_DATA_DIR=/local/scratch/$SLURM_JOB_ID  # thousands of small partitions - keep local
python run_all.py --jobs 4
```

`NSE_RAW_DIR` and `NSE_DATA_DIR` set the two roots independently because they want different
storage, and the raw corpus is shared with the BlockCrosser project so one copy is enough.
Neither directory is created when missing: raw data is an input, and silently creating an
empty one turns an unmounted share into a run that reports no raw file for every session.

Sessions are independent, so `--jobs` runs several at once. The memory and thread budget is
divided among the workers rather than left to each of them, which matters more than it
sounds: nsetick sizes its memory limit from total system memory and DuckDB does the same, so
four workers each helping themselves to a quarter of the machine is the whole of it. The
failure that causes is an allocation error several hours into a run.

The budget comes from what the process is actually allowed to use, not from what the node
has. `utils/resources.py` resolves it in order from `PIPELINE_MEMORY_MB` and `PIPELINE_CPUS`,
then the scheduler's own variables, then the cgroup limit, then the machine. On a cluster the
first three are what matter; `os.cpu_count()` reports the node and will be wrong.

Every run logs what it resolved and what it suggests:

```
=== resources: 32 cpus, 64.0 GiB usable (detected via SLURM, 20% reserved) ===
=== 4 job(s), 16.0 GiB and 8 threads each (suggested --jobs 8) ===
```

Start at the suggestion or below it. Memory is normally what binds: the per-session stages
hold a book for every symbol in the session.

Two things worth knowing when sizing an allocation. Keep the raw `.DAT.gz` files on shared
storage and the derived parquet on **local** scratch - raw access is sequential reads of large
files, which a network filesystem handles well, while the derived layers are thousands of
small symbol partitions, which it does not. And the pipeline resumes at session granularity,
so a job that hits a walltime limit loses only the session it was in the middle of.


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
session carries roughly 1,900 EQ symbols and the study uses a fraction of them.
`--universe-scan` keeps every symbol but only the trade tape, which is what the universe
builder ranks on.

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

### Typesetting somewhere else

A compute node rarely has LaTeX, and a laptop cannot hold the tick data. The report splits at
that seam: the analysis runs where the data is and records the quantities it computed, and
the typesetting runs where LaTeX is.

```bash
# wherever the data is - run.sh does this automatically if pdflatex is absent
python scripts/paper_bundle.py export

# on a machine with LaTeX
python scripts/paper_bundle.py import paper_bundle.tar.gz
python run_all.py --stage paper
```

The bundle is a few megabytes: result tables, the recorded quantities with their units and
provenance, and the universe selection. No parquet. Figures and macros are rebuilt on the
receiving side from those same result files, so a bundle cannot carry a figure that disagrees
with the numbers printed beside it.

`--stage paper` does not recompute anything, which is deliberate: recollecting on a machine
with no parsed data would overwrite every sample count with a zero, and the document would
report a study of nothing in perfectly good faith.

## Choosing the securities

Three groups, derived from the tape rather than hand-picked:

| Group | Derivatives | What it is for |
|---|---|---|
| `liquid` | yes | most traded underlyings; moving the settlement is expensive |
| `illiquid` | yes | least traded underlyings; the same incentive, far cheaper to act on |
| `placebo` | no | no contract settles against these, so an expiry effect here is a calendar effect |

```bash
python run_all.py --stage parse --universe-scan   # every EQ symbol, trades only
python scripts/build_universe.py --group-size 50
python run_all.py --jobs 4                        # the study, on the derived universe
```

The scan parses only the trade tape, because turnover, trade counts and price levels are all
the ranking needs. Scanning orders for every listed security as well would cost about a
hundred gigabytes for data nothing reads.

The placebo group is what separates a settlement effect from a last-Thursday-of-the-month
effect. Without it every result stays open to the second explanation, and the report says so.

Four things the selection gets right that a hand-picked list does not. Turnover is measured
on the **control sessions only**, so group membership does not depend on the expiry-day
behaviour being studied. Securities must trade in every session, clear an activity floor, and
hold a **stable turnover rank** across the year. The placebo group is matched to the illiquid
group on turnover **and price level**, because a spread in basis points depends on the tick
size relative to the price and a cheaper placebo group would show wider spreads for reasons
unrelated to expiry.

Derivatives eligibility cannot be read off the cash tape. Put the NSE list of F&O underlyings
in `config/fo_underlyings_2022.txt`, one symbol per line; that file documents where to get it.
Without it the builder produces the two derivative groups on turnover alone and no placebo
group, records `fo_verified: false`, and the report states the limitation.

Until the builder runs, `config/universe.py` falls back to a ten-name **development
universe** with no placebo group. It exists so the pipeline runs end to end; anything produced
on it is a smoke test, and the report says which universe it used.

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
