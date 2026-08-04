"""High-speed DuckDB fixed-width tick line parser (Stage 1)."""

import glob
from pathlib import Path
from typing import List

import duckdb

from config.schema_definitions import (
    CM_ORDERS_SCHEMA,
    CM_TRADES_SCHEMA,
    FAO_ORDERS_SCHEMA,
    FAO_TRADES_SCHEMA,
    FieldSchema,
)
from config.settings import (
    CASH_SERIES_FILTER,
    FUTURES_INSTRUMENT_FILTER,
    PARSED_DATA_DIR,
    RAW_DATA_DIR,
    TARGET_SYMBOLS_RAW,
)


def _build_select_exprs(schema: List[FieldSchema]) -> str:
    exprs: List[str] = []
    for field_name, start, length, dtype in schema:
        pos = start + 1  # DuckDB SUBSTRING is 1-indexed
        if dtype == "str":
            if field_name == "symbol":
                exprs.append(f"REGEXP_EXTRACT(SUBSTRING(line, {pos}, {length}), '[A-Z0-9-]+') AS symbol")
            elif field_name in ("series", "instrument", "option_type"):
                exprs.append(f"TRIM(SUBSTRING(line, {pos}, {length})) AS {field_name}")
            else:
                exprs.append(f"SUBSTRING(line, {pos}, {length}) AS {field_name}")
        elif dtype in ("int", "long"):
            exprs.append(f"TRY_CAST(TRIM(SUBSTRING(line, {pos}, {length})) AS BIGINT) AS {field_name}")
        else:
            exprs.append(f"TRIM(SUBSTRING(line, {pos}, {length})) AS {field_name}")
    return ",\n        ".join(exprs)


def _get_symbols_sql_list() -> str:
    symbols_quoted = [f"'{sym.strip()}'" for sym in TARGET_SYMBOLS_RAW]
    return ", ".join(symbols_quoted)


def parse_file_with_duckdb(
    date_str: str,
    category: str,
    schema: List[FieldSchema],
    sym_pos: int,
    type_pos: int,
    type_len: int,
    type_val: str,
    file_prefix: str,
) -> None:
    out_dir = Path(PARSED_DATA_DIR) / category / f"date={date_str}"
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"[SKIP] {category.upper()} for date={date_str} already parsed.")
        return

    pattern = str(Path(RAW_DATA_DIR) / f"{file_prefix}_{date_str}*.DAT*")
    matched = glob.glob(pattern)
    valid_files = [m.replace("\\", "/") for m in matched if not m.endswith(".trg")]

    if not valid_files:
        if category == "fao_orders":
            print(f"[INFO] Optional {category.upper()} for date={date_str} omitted (not required for pipeline analysis).")
        else:
            print(f"[WARN] No raw file matching {pattern} found.")
        return

    if len(valid_files) == 1:
        file_spec = f"'{valid_files[0]}'"
        print(f"[PARSE-DUCKDB] {category.upper()} for date={date_str} -> {valid_files[0]}")
    else:
        file_spec = str(valid_files)
        print(f"[PARSE-DUCKDB] {category.upper()} for date={date_str} -> {len(valid_files)} files: {file_prefix}_{date_str}*")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_parquet = str((out_dir / "data.parquet")).replace("\\", "/")

    select_sql = _build_select_exprs(schema)
    symbols_sql = _get_symbols_sql_list()

    query = f"""
    SELECT 
        {select_sql}
    FROM read_csv({file_spec}, header=False, sep='\\n', columns={{'line': 'VARCHAR'}}, auto_detect=False)
    WHERE REGEXP_EXTRACT(SUBSTRING(line, {sym_pos}, 10), '[A-Z0-9-]+') IN ({symbols_sql})
      AND TRIM(SUBSTRING(line, {type_pos}, {type_len})) = '{type_val}'
    """

    try:
        with duckdb.connect() as conn:
            copy_sql = f"COPY ({query}) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION 'SNAPPY', OVERWRITE_OR_IGNORE 1);"
            conn.execute(copy_sql)
        print(f"[DONE-DUCKDB] Saved parsed {category} to {out_parquet}")
    except Exception as exc:
        print(f"[ERROR-DUCKDB] Failed to parse {category} for date={date_str}: {exc}")


def parse_cash_orders_duckdb(date_str: str) -> None:
    parse_file_with_duckdb(
        date_str=date_str,
        category="cash_orders",
        schema=CM_ORDERS_SCHEMA,
        sym_pos=39,
        type_pos=49,
        type_len=2,
        type_val=CASH_SERIES_FILTER,
        file_prefix="CASH_Orders",
    )


def parse_cash_trades_duckdb(date_str: str) -> None:
    parse_file_with_duckdb(
        date_str=date_str,
        category="cash_trades",
        schema=CM_TRADES_SCHEMA,
        sym_pos=37,
        type_pos=47,
        type_len=2,
        type_val=CASH_SERIES_FILTER,
        file_prefix="CASH_Trades",
    )


def parse_fao_orders_duckdb(date_str: str) -> None:
    parse_file_with_duckdb(
        date_str=date_str,
        category="fao_orders",
        schema=FAO_ORDERS_SCHEMA,
        sym_pos=39,
        type_pos=49,
        type_len=6,
        type_val=FUTURES_INSTRUMENT_FILTER,
        file_prefix="FAO_Orders",
    )


def parse_fao_trades_duckdb(date_str: str) -> None:
    parse_file_with_duckdb(
        date_str=date_str,
        category="fao_trades",
        schema=FAO_TRADES_SCHEMA,
        sym_pos=38,
        type_pos=48,
        type_len=6,
        type_val=FUTURES_INSTRUMENT_FILTER,
        file_prefix="FAO_Trades",
    )


def run_duckdb_parser_for_date(date_str: str) -> None:
    parse_cash_orders_duckdb(date_str)
    parse_cash_trades_duckdb(date_str)
    parse_fao_orders_duckdb(date_str)
    parse_fao_trades_duckdb(date_str)
