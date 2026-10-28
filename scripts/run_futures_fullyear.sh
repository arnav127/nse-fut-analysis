#!/bin/bash
# The derivatives analyses on all twelve monthly expiries, now that the library's other shares
# carry the F&O files for the whole year. Run on the HPC after `python scripts/fao_links.py`
# and after linking the session's FAO_Trades files into $NSE_RAW_DIR.
set -e
source ~/sandbox/tools/pc_env.sh
python - <<'PY'
from config.settings import ALL_TARGET_DATES
from stage1_parse.tick_parser import parse_category
for session in ALL_TARGET_DATES:
    out = parse_category(session, "fao_trades")
    print(session, out, flush=True)
PY
python -m stage9_tape.futures_tape
python -m stage6_insights.s7_futures_convergence
python -m stage6_insights.s8_strike_pinning
python -m stage9_tape.futures_book
echo "futures full year done"
