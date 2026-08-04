"""Orchestrator for Stage 1 tick data parsing."""

from typing import Optional
from config.settings import ALL_TARGET_DATES
from stage1_parse.duckdb_parser import run_duckdb_parser_for_date


def run_parse(single_date: Optional[str] = None) -> None:
    dates_to_process = [single_date] if single_date else ALL_TARGET_DATES
    print("\n=== STAGE 1: HIGH-SPEED TICK DATA PARSING ===")

    for date_str in dates_to_process:
        print(f"\n=== Processing Date: {date_str} ===")
        run_duckdb_parser_for_date(date_str)

    print("\n[COMPLETE] Stage 1 parsing finished.")


if __name__ == "__main__":
    run_parse()
