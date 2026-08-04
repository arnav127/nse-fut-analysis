"""
run_parse_all.py — Orchestrate Stage 1 parsing across dates using DuckDB zero-JVM C++ engine.
"""
from config.settings import ALL_TARGET_DATES
from stage1_parse.duckdb_parser import run_duckdb_parser_for_date

def run_parse(single_date=None, engine="duckdb"):
    """
    Run parsing for all dates or a single specified date via zero-JVM DuckDB C++ engine.
    """
    dates_to_process = [single_date] if single_date else ALL_TARGET_DATES
    print(f"\n=== STAGE 1: HIGH-SPEED PARSING (Engine: {engine.upper()}) ===")

    for d in dates_to_process:
        print(f"\n=== Processing Date: {d} ===")
        run_duckdb_parser_for_date(d)

    print("\n[COMPLETE] Stage 1 parsing process finished.")

if __name__ == "__main__":
    run_parse(engine="duckdb")
