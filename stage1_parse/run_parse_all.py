"""Orchestrator for Stage 1 tick data parsing."""

import time
from typing import Optional

from config.settings import ALL_TARGET_DATES
from stage1_parse.duckdb_parser import run_duckdb_parser_for_date


def run_parse(single_date: Optional[str] = None) -> None:
    dates_to_process = [single_date] if single_date else ALL_TARGET_DATES
    print("\n=== STAGE 1: HIGH-SPEED TICK DATA PARSING ===")

    t_start = time.time()
    for date_str in dates_to_process:
        t_date = time.time()
        print(f"\n=== Processing Date: {date_str} ===")
        run_duckdb_parser_for_date(date_str)
        print(f"[TIMING] Date {date_str} parsed in {time.time() - t_date:.2f}s")

    print(f"\n[COMPLETE] Stage 1 parsing finished in {time.time() - t_start:.2f}s")


if __name__ == "__main__":
    run_parse()
