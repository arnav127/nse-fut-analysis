"""
duckdb_enricher.py — High-speed, low-memory DuckDB engine for Stage 2 (Enrichment -> Partitioned Parquet).
Enriches timestamps, prices, and labels, and partitions by (symbol, trade_date) in C++ without initializing JVM.
"""
import os
import glob
import duckdb
from config.settings import (
    PARSED_DATA_DIR, ENRICHED_DATA_DIR, EXPIRY_THURSDAYS_DDMMYYYY,
    SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
)

def _get_expiry_sql_list():
    return ", ".join([f"'{d}'" for d in EXPIRY_THURSDAYS_DDMMYYYY])

def _build_price_exprs(columns):
    price_cols = {"limit_price", "trigger_price", "trade_price", "strike_price"}
    exprs = []
    for col in columns:
        if col in price_cols:
            exprs.append(f"CAST({col} AS DOUBLE) / 100.0 AS {col}")
        else:
            exprs.append(col)
    return exprs

def enrich_category_duckdb(category):
    parsed_path = os.path.join(PARSED_DATA_DIR, category).replace("\\", "/")
    out_path = os.path.join(ENRICHED_DATA_DIR, category).replace("\\", "/")

    # Check if there are any parquet files in parsed_path
    parquet_pattern = f"{parsed_path}/*/*.parquet"
    matched = glob.glob(parquet_pattern)
    if not matched:
        print(f"[SKIP-DUCKDB] No parsed parquet files found for {category} in {parsed_path}")
        return

    print(f"[ENRICH-DUCKDB] Enriching {category.upper()} -> {out_path} ...")
    os.makedirs(out_path, exist_ok=True)

    conn = duckdb.connect()
    try:
        # Get list of columns in source parquet
        schema_df = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_pattern}')").df()
        base_cols = list(schema_df["column_name"])

        # Prepare price conversion exprs
        base_select = _build_price_exprs(base_cols)

        # Mappings SQL depending on whether it is Orders or Trades
        extra_cols = []
        if "client_identity" in base_cols:
            extra_cols.append("""
            CASE client_identity 
                WHEN 1 THEN 'Custodian' 
                WHEN 2 THEN 'Proprietary' 
                WHEN 3 THEN 'NCNP' 
                ELSE 'Unknown' 
            END AS participant_type
            """)
        if "buy_client_identity" in base_cols:
            extra_cols.append("""
            CASE buy_client_identity 
                WHEN 1 THEN 'Custodian' 
                WHEN 2 THEN 'Proprietary' 
                WHEN 3 THEN 'NCNP' 
                ELSE 'Unknown' 
            END AS buy_participant_type
            """)
            extra_cols.append("""
            CASE sell_client_identity 
                WHEN 1 THEN 'Custodian' 
                WHEN 2 THEN 'Proprietary' 
                WHEN 3 THEN 'NCNP' 
                ELSE 'Unknown' 
            END AS sell_participant_type
            """)
        if "algo_indicator" in base_cols:
            extra_cols.append("""
            CASE algo_indicator 
                WHEN 0 THEN 'Algo' 
                WHEN 1 THEN 'Non-Algo' 
                WHEN 2 THEN 'Algo-SOR' 
                WHEN 3 THEN 'Non-Algo-SOR' 
                ELSE 'Unknown' 
            END AS algo_type
            """)
        if "buy_algo_indicator" in base_cols:
            extra_cols.append("""
            CASE buy_algo_indicator 
                WHEN 0 THEN 'Algo' 
                WHEN 1 THEN 'Non-Algo' 
                WHEN 2 THEN 'Algo-SOR' 
                WHEN 3 THEN 'Non-Algo-SOR' 
                ELSE 'Unknown' 
            END AS buy_algo_type
            """)
            extra_cols.append("""
            CASE sell_algo_indicator 
                WHEN 0 THEN 'Algo' 
                WHEN 1 THEN 'Non-Algo' 
                WHEN 2 THEN 'Algo-SOR' 
                WHEN 3 THEN 'Non-Algo-SOR' 
                ELSE 'Unknown' 
            END AS sell_algo_type
            """)
        if "activity_type" in base_cols:
            extra_cols.append("""
            CASE activity_type 
                WHEN 1 THEN 'Entry' 
                WHEN 3 THEN 'Cancel' 
                WHEN 4 THEN 'Modify' 
                ELSE 'Unknown' 
            END AS activity_label
            """)

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
    except Exception as e:
        print(f"[ERROR-DUCKDB] Failed to enrich {category}: {e}")
    finally:
        conn.close()

def run_duckdb_enrich_all():
    for category in ["cash_orders", "cash_trades", "fao_orders", "fao_trades"]:
        enrich_category_duckdb(category)
