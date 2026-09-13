#!/usr/bin/env bash
#
# Everything, from the raw exchange files to the compiled report.
#
#   ./run.sh                 run it
#   ./run.sh --status        ask what is already done, change nothing
#   ./run.sh --stage report  one stage (any run_all.py flag is forwarded)
#   sbatch run.sh            submit it, using the directives below
#
# Edit the block marked SETTINGS and run. Anything already exported in the environment wins
# over the value here, so a one-off change needs no edit:
#
#   JOBS=8 ./run.sh
#
# The pipeline resumes at session granularity, so re-running after an interruption picks up
# where it stopped rather than starting again. That also means this script is safe to run
# twice.

#SBATCH --job-name=nse-expiry
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=7-00:00:00
#SBATCH --output=logs/slurm-%j.out
# Adjust the directives above for your cluster - partition and account names in particular.
# They are comments to bash, so running the script directly ignores them.

set -euo pipefail

# ============================== SETTINGS ==============================

# Where the raw .DAT.gz files are. Sequential reads of very large compressed files, so a
# network filesystem is fine, and both projects read the same corpus - one copy is enough.
export NSE_RAW_DIR="${NSE_RAW_DIR:-/shared/nse/raw}"

# Where everything this pipeline writes goes. Thousands of small symbol partitions per
# session: metadata-bound, and much faster on a local disk than on a network share.
export NSE_DATA_DIR="${NSE_DATA_DIR:-$PWD/data}"

# Sessions processed at once. The memory and thread budget is split between them, so this
# is the main knob. Four is right for 32 cores and 64 GB; run.sh prints what the pipeline
# would suggest for the allocation it detects.
JOBS="${JOBS:-4}"

# Securities per group: most-traded derivatives underlyings, least-traded ones, and a
# matched set with no derivative at all.
GROUP_SIZE="${GROUP_SIZE:-50}"

# auto - build the universe only if it does not exist yet
# yes  - rebuild it, which means a full cross-section scan of the trade tape
# no   - use whatever config/universe_2022.json holds, or the development list
BUILD_UNIVERSE="${BUILD_UNIVERSE:-auto}"

# Override what the pipeline thinks it may use. Leave empty to let it detect the allocation
# from SLURM, then the cgroup limit, then the machine.
# export PIPELINE_CPUS=32
# export PIPELINE_MEMORY_MB=65536

# Cluster-specific setup. Uncomment what applies.
# module load python/3.13
# source /path/to/venv/bin/activate

PYTHON="${PYTHON:-python3}"

# ======================== END OF SETTINGS =============================

cd "$(dirname "$0")"
mkdir -p logs
RUN_LOG="logs/run-$(date +%Y%m%d-%H%M%S).log"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

# DuckDB spills here when a query exceeds its memory limit. Left unset it lands in the
# working directory, which on a cluster is often a slow, quota-limited network share - and
# the failure surfaces as a confusing write error rather than as a disk-full one.
export TMPDIR="${TMPDIR:-$NSE_DATA_DIR/tmp}"
mkdir -p "$TMPDIR"

say "checks"
command -v "$PYTHON" >/dev/null || fail "$PYTHON not found. Set PYTHON, or load your module."
"$PYTHON" -c 'import nsetick' 2>/dev/null || fail \
  "nsetick is not importable. Build and install the wheel:
     cd ../nsetick && maturin build --release -m crates/nsetick-py/Cargo.toml
     pip install ../nsetick/target/wheels/nsetick-*.whl"
[ -d "$NSE_RAW_DIR" ] || fail "NSE_RAW_DIR does not exist: $NSE_RAW_DIR"

raw_count=$(find "$NSE_RAW_DIR" -maxdepth 1 -name '*.DAT*' ! -name '*.trg' 2>/dev/null | wc -l)
[ "$raw_count" -gt 0 ] || fail "no .DAT.gz files in $NSE_RAW_DIR"

printf '  raw       %s (%s files)\n' "$NSE_RAW_DIR" "$raw_count"
printf '  data      %s\n' "$NSE_DATA_DIR"
printf '  spill     %s\n' "$TMPDIR"
printf '  jobs      %s\n' "$JOBS"
printf '  log       %s\n' "$RUN_LOG"
"$PYTHON" -c 'from utils.resources import describe, suggested_jobs
print(f"  detected  {describe()}")
print(f"  suggested --jobs {suggested_jobs()}")'

# Any argument means "do this one thing" - a stage, a status query, a single session - so
# the universe step is skipped and the arguments are forwarded untouched.
if [ "$#" -gt 0 ]; then
  say "run_all.py $*"
  # Not `exec`: in a pipeline it replaces only the subshell running that element, so the
  # script would carry on to the steps below - which is how a "--stage clob" invocation
  # ended up rebuilding the universe.
  "$PYTHON" run_all.py --jobs "$JOBS" "$@" 2>&1 | tee -a "$RUN_LOG"
  exit "${PIPESTATUS[0]}"
fi

started=$SECONDS

build_universe=false
case "$BUILD_UNIVERSE" in
  yes)  build_universe=true ;;
  no)   build_universe=false ;;
  auto) [ -f config/universe_2022.json ] || build_universe=true ;;
  *)    fail "BUILD_UNIVERSE must be auto, yes or no (got '$BUILD_UNIVERSE')" ;;
esac

if $build_universe; then
  say "universe: scanning the cross-section (trades only)"
  # Trades alone, because turnover, trade counts and price levels are all the ranking needs.
  # Scanning orders for every listed security would cost about a hundred gigabytes for data
  # nothing reads.
  "$PYTHON" run_all.py --stage parse --universe-scan --jobs "$JOBS" 2>&1 | tee -a "$RUN_LOG"

  say "universe: selecting $GROUP_SIZE securities per group"
  "$PYTHON" scripts/build_universe.py --group-size "$GROUP_SIZE" 2>&1 | tee -a "$RUN_LOG"
else
  say "universe: using the existing selection"
fi

say "pipeline"
"$PYTHON" run_all.py --jobs "$JOBS" 2>&1 | tee -a "$RUN_LOG"

elapsed=$(( SECONDS - started ))
say "done in $(( elapsed / 3600 ))h $(( (elapsed % 3600) / 60 ))m"
printf '  report    %s\n' "$NSE_DATA_DIR/results/final_research_paper.pdf"
printf '  log       %s\n' "$RUN_LOG"
