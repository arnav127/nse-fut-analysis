"""
clob_builder.py — Replay orders & trades chronologically for a (symbol, date) pair via DuckDB C++ engine.

Optimizations:
1. Replaced Pandas read_parquet + pd.concat + sort_values with zero-copy DuckDB SQL UNION ALL + ORDER BY.
2. Orders and trades are merged into a single event stream sorted by txn_time_jiffies in C++.
3. Uses C++ PyBind11 OrderBook engine when compiled or fast Numba/Python fallback.
"""
import os
import duckdb
import pandas as pd
import numpy as np
from config.settings import ENRICHED_DATA_DIR, CLOB_DATA_DIR, SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
from stage4_clob.order_book import OrderBook

def build_clob_for_symbol_date(symbol, date_str):
    """
    Replay orders and trades in strict timestamp order using DuckDB SQL, emitting 1-second snapshots
    during the 15:00:00 to 15:30:00 settlement window.
    """
    out_dir = os.path.join(CLOB_DATA_DIR, symbol, f"date={date_str}")
    out_file = os.path.join(out_dir, "snapshots.parquet")
    if os.path.exists(out_file):
        return

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders").replace("\\", "/")
    trades_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades").replace("\\", "/")

    if not os.path.exists(os.path.join(ENRICHED_DATA_DIR, "cash_orders")) or \
       not os.path.exists(os.path.join(ENRICHED_DATA_DIR, "cash_trades")):
        return

    # 1. Build unified chronological event stream via DuckDB C++ SQL
    query = f"""
    WITH orders_ev AS (
        SELECT 
            1 AS event_kind,
            trade_time,
            order_number,
            activity_type,
            buy_sell,
            limit_price,
            volume_original,
            0 AS buy_order_number,
            0 AS sell_order_number,
            0 AS trade_quantity,
            txn_datetime,
            activity_label,
            txn_time_jiffies
        FROM read_parquet('{orders_path}/*/*.parquet')
        WHERE symbol = '{symbol}' AND trade_date = '{date_str}'
    ),
    trades_ev AS (
        SELECT 
            2 AS event_kind,
            trade_time,
            0 AS order_number,
            0 AS activity_type,
            '' AS buy_sell,
            0.0 AS limit_price,
            0 AS volume_original,
            buy_order_number,
            sell_order_number,
            trade_quantity,
            txn_datetime,
            'Trade' AS activity_label,
            txn_time_jiffies
        FROM read_parquet('{trades_path}/*/*.parquet')
        WHERE symbol = '{symbol}' AND trade_date = '{date_str}'
    )
    SELECT * FROM orders_ev
    UNION ALL
    SELECT * FROM trades_ev
    ORDER BY txn_time_jiffies, event_kind
    """

    conn = duckdb.connect()
    try:
        combined_events = conn.execute(query).df()
    except Exception:
        conn.close()
        return
    finally:
        conn.close()

    if combined_events.empty:
        return

    book = OrderBook()
    snapshots = []
    last_snap_second = -1

    # 2. Replay loop using fast columnar iteration
    cols_order = [
        "event_kind", "trade_time", "order_number", "activity_type", "buy_sell",
        "limit_price", "volume_original", "buy_order_number", "sell_order_number",
        "trade_quantity", "txn_datetime", "activity_label"
    ]
    for ev in combined_events[cols_order].itertuples(index=False):
        event_kind = ev.event_kind
        t_time = ev.trade_time

        if event_kind == 1:
            book.process_event(
                ev.order_number,
                int(ev.activity_type),
                ev.buy_sell,
                float(ev.limit_price),
                int(ev.volume_original)
            )
        elif event_kind == 2:
            t_qty = int(ev.trade_quantity)
            book.remove_traded_qty(ev.buy_order_number, t_qty)
            book.remove_traded_qty(ev.sell_order_number, t_qty)

        # Emit 1-second snapshots during settlement window
        if SETTLEMENT_WINDOW_START <= t_time <= SETTLEMENT_WINDOW_END:
            h, m, s = map(int, t_time.split(":"))
            sec_from_1500 = (h - 15) * 3600 + m * 60 + s

            if sec_from_1500 != last_snap_second:
                last_snap_second = sec_from_1500
                snap = book.snapshot(depth=10)
                snap["symbol"] = symbol
                snap["trade_date"] = date_str
                snap["seconds_from_1500"] = sec_from_1500
                snap["snapshot_time"] = f"{h:02d}:{m:02d}:{s:02d}"
                snapshots.append(snap)

    if snapshots:
        df_snaps = pd.DataFrame(snapshots)
        os.makedirs(out_dir, exist_ok=True)
        df_snaps.to_parquet(out_file, engine="pyarrow", index=False)
        print(f"[CLOB BUILT - DUCKDB] {symbol} on {date_str}: {len(snapshots)} snapshots generated -> {out_file}")
