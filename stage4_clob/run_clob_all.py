"""
run_clob_all.py — Multiprocessing orchestrator for Stage 4 CLOB reconstruction.
"""
from multiprocessing import Pool
from config.settings import ALL_TARGET_DATES, TARGET_SYMBOLS, CLOB_PARALLEL_WORKERS
from stage4_clob.clob_builder import build_clob_for_symbol_date

def _build_worker(args):
    symbol, date_str = args
    build_clob_for_symbol_date(symbol, date_str)

def run_clob(single_date=None, single_symbol=None):
    symbols = [single_symbol] if single_symbol else TARGET_SYMBOLS
    dates = [single_date] if single_date else ALL_TARGET_DATES

    tasks = [(s, d) for s in symbols for d in dates]
    print(f"\n=== STAGE 4: CLOB RECONSTRUCTION ({len(tasks)} tasks on {CLOB_PARALLEL_WORKERS} workers) ===")

    with Pool(CLOB_PARALLEL_WORKERS) as pool:
        pool.map(_build_worker, tasks)

    print("\n[COMPLETE] Stage 4 CLOB reconstruction finished.")

if __name__ == "__main__":
    run_clob()
