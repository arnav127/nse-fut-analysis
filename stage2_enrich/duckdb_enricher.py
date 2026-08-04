"""DuckDB microstructure dataset enrichment and partitioning engine (Stage 2)."""

import glob
from pathlib import Path
from typing import List

import duckdb

from config.settings import (
    ENRICHED_DATA_DIR,
    EXPIRY_THURSDAYS_DDMMYYYY,
    PARSED_DATA_DIR,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
)


def _get_expiry_sql_list() -> str:
    return ", ".join(f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY)


def _build_price_exprs(columns: List[str]) -> List[str]:
    price_cols = {"limit_price", "trigger_price", "trade_price", "strike_price"}
    return [
        f"CAST({col} AS DOUBLE) / 100.0 AS {col}" if col in price_cols else col
        for col in columns
    ]


def enrich_category_duckdb(category: str) -> None:
    parsed_path = str(Path(PARSED_DATA_DIR) / category).replace("\\", "/")
    out_path = str(Path(ENRICHED_DATA_DIR) / category).replace("\\", "/")

    parquet_pattern = f"{parsed_path}/*/*.parquet"
    if not glob.glob(parquet_pattern):
        print(f"[SKIP-DUCKDB] No parsed parquet files found for {category}")
        return

    print(f"[ENRICH-DUCKDB] Enriching {category.upper()} -> {out_path}")
    Path(out_path).mkdir(parents=True, exist_ok=True)

    try:
        with duckdb.connect() as conn:
            schema_df = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_pattern}')").df()
            base_cols = list(schema_df["column_name"])
            base_select = _build_price_exprs(base_cols)

            extra_cols: List[str] = []
            if "client_identity" in base_cols:
                extra_cols.append(
                    "CASE client_identity WHEN 1 THEN 'Custodian' WHEN 2 THEN 'Proprietary' WHEN 3 THEN 'NCNP' ELSE 'Unknown' END AS participant_type"
                )
            if "buy_client_identity" in base_cols:
                extra_cols.append(
                    "CASE buy_client_identity WHEN 1 THEN 'Custodian' WHEN 2 THEN 'Proprietary' WHEN 3 THEN 'NCNP' ELSE 'Unknown' END AS buy_participant_type"
                )
                extra_cols.append(
                    "CASE sell_client_identity WHEN 1 THEN 'Custodian' WHEN 2 THEN 'Proprietary' WHEN 3 THEN 'NCNP' ELSE 'Unknown' END AS sell_participant_type"
                )
            if "algo_indicator" in base_cols:
                extra_cols.append(
                    "CASE algo_indicator WHEN 0 THEN 'Algo' WHEN 1 THEN 'Non-Algo' WHEN 2 THEN 'Algo-SOR' WHEN 3 THEN 'Non-Algo-SOR' ELSE 'Unknown' END AS algo_type"
                )
            if "buy_algo_indicator" in base_cols:
                extra_cols.append(
                    "CASE buy_algo_indicator WHEN 0 THEN 'Algo' WHEN 1 THEN 'Non-Algo' WHEN 2 THEN 'Algo-SOR' WHEN 3 THEN 'Non-Algo-SOR' ELSE 'Unknown' END AS buy_algo_type"
                )
                extra_cols.append(
                    "CASE sell_algo_indicator WHEN 0 THEN 'Algo' WHEN 1 THEN 'Non-Algo' WHEN 2 THEN 'Algo-SOR' WHEN 3 THEN 'Non-Algo-SOR' ELSE 'Unknown' END AS sell_algo_type"
                )
            if "activity_type" in base_cols:
                extra_cols.append(
                    "CASE activity_type WHEN 1 THEN 'Entry' WHEN 3 THEN 'Cancel' WHEN 4 THEN 'Modify' ELSE 'Unknown' END AS activity_label"
                )

            extra_cols_sql = ",\n            ".join(extra_cols) if extra_cols else "'' AS extra_dummy"
            expiry_list = _get_expiry_sql_list()

            query = f"""
            WITH base AS (
                SELECT 
                    {', '.join(base_select)},
                    TIMESTAMP '1980-01-01 00:00:00' + (txn_time_jiffies / 65536.0) * INTERVAL 1 SECOND AS txn_datetime
                FROM read_parquet('{parquet_pattern}')
            )
            SELECT 
                *,
                strftime(txn_datetime, '%Y-%m-%d') AS trade_date,
                strftime(txn_datetime, '%H:%M:%S') AS trade_time,
                strftime(txn_datetime, '%H:%M:00') AS time_bucket,
                (strftime(txn_datetime, '%H:%M:%S') >= '{SETTLEMENT_WINDOW_START}' AND 
                 strftime(txn_datetime, '%H:%M:%S') <= '{SETTLEMENT_WINDOW_END}') AS is_settlement_window,
                (strftime(txn_datetime, '%d%m%Y') IN ({expiry_list})) AS is_expiry,
                {extra_cols_sql}
            FROM base
            """

            copy_sql = f"""
            COPY ({query}) TO '{out_path}' (
                FORMAT PARQUET, 
                COMPRESSION 'SNAPPY', 
                PARTITION_BY (symbol, trade_date), 
                OVERWRITE_OR_IGNORE 1
            );
            """
            conn.execute(copy_sql)
            print(f"[DONE-DUCKDB] Enriched and partitioned {category} to {out_path}")
    except Exception as exc:
        print(f"[ERROR-DUCKDB] Failed to enrich {category}: {exc}")


def run_duckdb_enrich_all() -> None:
    for category in ("cash_orders", "cash_trades", "fao_orders", "fao_trades"):
        enrich_category_duckdb(category)
