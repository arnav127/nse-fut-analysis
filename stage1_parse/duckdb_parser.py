"""
duckdb_parser.py — High-speed, low-memory DuckDB engine for Stage 1 (.DAT.gz -> .parquet).
Streams fixed-width text files in C++ without loading full files into RAM or initializing JVM.
"""
import os
import glob
import duckdb
from config.settings import (
    RAW_DATA_DIR, PARSED_DATA_DIR, TARGET_SYMBOLS_RAW, CASH_SERIES_FILTER, FUTURES_INSTRUMENT_FILTER
)
from config.schema_definitions import (
    CM_ORDERS_SCHEMA, CM_TRADES_SCHEMA, FAO_ORDERS_SCHEMA, FAO_TRADES_SCHEMA
)

def _build_select_exprs(schema):
    exprs = []
    for field_name, start, length, dtype in schema:
        pos = start + 1  # DuckDB SUBSTRING is 1-indexed
        if dtype == "str":
            if field_name in ("symbol", "series", "instrument", "option_type"):
                exprs.append(f"TRIM(SUBSTRING(line, {pos}, {length})) AS {field_name}")
            else:
                exprs.append(f"SUBSTRING(line, {pos}, {length}) AS {field_name}")
        elif dtype in ("int", "long"):
            exprs.append(f"TRY_CAST(TRIM(SUBSTRING(line, {pos}, {length})) AS BIGINT) AS {field_name}")
        else:
            exprs.append(f"TRIM(SUBSTRING(line, {pos}, {length})) AS {field_name}")
    return ",\n        ".join(exprs)

def _get_symbols_sql_list():
    symbols_quoted = [f"'{sym.strip()}'" for sym in TARGET_SYMBOLS_RAW]
    return ", ".join(symbols_quoted)

def parse_file_with_duckdb(date_str, category, schema, sym_pos, type_pos, type_len, type_val, file_prefix):
    """
    Generic DuckDB fixed-width parser for Cash / F&O Orders & Trades.
    """
    out_dir = os.path.join(PARSED_DATA_DIR, category, f"date={date_str}")
    if os.path.exists(out_dir) and len(os.listdir(out_dir)) > 0:
        print(f"[SKIP] {category.upper()} for date={date_str} already parsed.")
        return

    # Look for matching .DAT.gz or .DAT file in RAW_DATA_DIR
    pattern = os.path.join(RAW_DATA_DIR, f"{file_prefix}_{date_str}*.DAT*")
    matched = glob.glob(pattern)
    if not matched:
        print(f"[WARN] No raw file matching {pattern} found.")
        return

    in_file = matched[0].replace("\\", "/")
    print(f"[PARSE-DUCKDB] {category.upper()} for date={date_str} -> {in_file} ...")

    os.makedirs(out_dir, exist_ok=True)
    out_parquet = os.path.join(out_dir, "data.parquet").replace("\\", "/")

    select_sql = _build_select_exprs(schema)
    symbols_sql = _get_symbols_sql_list()

    query = f"""
    SELECT 
        {select_sql}
    FROM read_csv('{in_file}', header=False, sep='\\n', columns={{'line': 'VARCHAR'}}, auto_detect=False)
    WHERE TRIM(SUBSTRING(line, {sym_pos}, 10)) IN ({symbols_sql})
      AND TRIM(SUBSTRING(line, {type_pos}, {type_len})) = '{type_val}'
    """

    conn = duckdb.connect()
    try:
        copy_sql = f"""
        COPY ({query}) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION 'SNAPPY', OVERWRITE_OR_IGNORE 1);
        """
        conn.execute(copy_sql)
        print(f"[DONE-DUCKDB] Saved parsed {category} to {out_parquet}")
    except Exception as e:
        print(f"[ERROR-DUCKDB] Failed to parse {category} for date={date_str}: {e}")
    finally:
        conn.close()

def parse_cash_orders_duckdb(date_str):
    # CM_ORDERS: symbol starts at 38 (pos 39), series at 48 (pos 49, len 2)
    parse_file_with_duckdb(
        date_str=date_str,
        category="cash_orders",
        schema=CM_ORDERS_SCHEMA,
        sym_pos=39,
        type_pos=49,
        type_len=2,
        type_val=CASH_SERIES_FILTER,
        file_prefix="CASH_Orders"
    )

def parse_cash_trades_duckdb(date_str):
    # CM_TRADES: symbol starts at 36 (pos 37), series at 46 (pos 47, len 2)
    parse_file_with_duckdb(
        date_str=date_str,
        category="cash_trades",
        schema=CM_TRADES_SCHEMA,
        sym_pos=37,
        type_pos=47,
        type_len=2,
        type_val=CASH_SERIES_FILTER,
        file_prefix="CASH_Trades"
    )

def parse_fao_orders_duckdb(date_str):
    # FAO_ORDERS: symbol starts at 38 (pos 39), instrument at 48 (pos 49, len 6)
    parse_file_with_duckdb(
        date_str=date_str,
        category="fao_orders",
        schema=FAO_ORDERS_SCHEMA,
        sym_pos=39,
        type_pos=49,
        type_len=6,
        type_val=FUTURES_INSTRUMENT_FILTER,
        file_prefix="FAO_Orders"
    )

def parse_fao_trades_duckdb(date_str):
    # FAO_TRADES: symbol starts at 37 (pos 38), instrument at 47 (pos 48, len 6)
    parse_file_with_duckdb(
        date_str=date_str,
        category="fao_trades",
        schema=FAO_TRADES_SCHEMA,
        sym_pos=38,
        type_pos=48,
        type_len=6,
        type_val=FUTURES_INSTRUMENT_FILTER,
        file_prefix="FAO_Trades"
    )

def run_duckdb_parser_for_date(date_str):
    parse_cash_orders_duckdb(date_str)
    parse_cash_trades_duckdb(date_str)
    parse_fao_orders_duckdb(date_str)
    parse_fao_trades_duckdb(date_str)
