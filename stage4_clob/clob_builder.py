"""
clob_builder.py — Replay orders & trades chronologically for a (symbol, date) pair.

CRITICAL FIX: Orders and trades are merged into a single event stream sorted by
txn_time_jiffies. Limit orders are reduced AT THE EXACT TIME of trade execution,
preventing premature order removal and book corruption.
"""
import os
import pandas as pd
import numpy as np
from config.settings import ENRICHED_DATA_DIR, CLOB_DATA_DIR, SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
from stage4_clob.order_book import OrderBook

def build_clob_for_symbol_date(symbol, date_str):
    """
    Replay orders and trades in strict timestamp order, emitting 1-second snapshots
    during the 15:00:00 to 15:30:00 settlement window.
    """
    out_dir = os.path.join(CLOB_DATA_DIR, symbol, f"date={date_str}")
    out_file = os.path.join(out_dir, "snapshots.parquet")
    if os.path.exists(out_file):
        return

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    trades_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")

    if not os.path.exists(orders_path) or not os.path.exists(trades_path):
        return

    # Load orders and trades for this date & symbol
    try:
        df_orders = pd.read_parquet(orders_path, filters=[("symbol", "==", symbol)])
        df_trades = pd.read_parquet(trades_path, filters=[("symbol", "==", symbol)])
    except Exception:
        return

    if df_orders.empty:
        return

    # 1. Build unified chronological event stream
    # Event types: 1=Order Event, 2=Trade Execution
    order_events = df_orders[[
        "order_number", "activity_type", "buy_sell", "limit_price",
        "volume_original", "txn_time_jiffies", "trade_time", "txn_datetime", "activity_label"
    ]].copy()
    order_events["event_kind"] = 1
    order_events["buy_order_number"] = 0
    order_events["sell_order_number"] = 0
    order_events["trade_quantity"] = 0

    if not df_trades.empty:
        trade_events = df_trades[[
            "buy_order_number", "sell_order_number", "trade_quantity",
            "txn_time_jiffies", "trade_time", "txn_datetime"
        ]].copy()
        trade_events["event_kind"] = 2
        trade_events["order_number"] = 0
        trade_events["activity_type"] = 0
        trade_events["buy_sell"] = ""
        trade_events["limit_price"] = 0.0
        trade_events["volume_original"] = 0
        trade_events["activity_label"] = "Trade"

        combined_events = pd.concat([order_events, trade_events], ignore_index=True)
    else:
        combined_events = order_events

    # Sort stream by txn_time_jiffies, breaking ties by event_kind (order entry before trade execution)
    combined_events = combined_events.sort_values(
        by=["txn_time_jiffies", "event_kind"],
        ascending=[True, True]
    ).reset_index(drop=True)

    book = OrderBook()
    snapshots = []
    last_snap_second = -1

    # 2. Replay loop using fast columnar iteration (~50x faster than df.iterrows())
    cols_order = [
        "event_kind", "trade_time", "order_number", "activity_type", "buy_sell",
        "limit_price", "volume_original", "buy_order_number", "sell_order_number",
        "trade_quantity", "txn_datetime", "activity_label"
    ]
    for ev in combined_events[cols_order].itertuples(index=False):
        event_kind = ev.event_kind
        t_time = ev.trade_time

        if event_kind == 1:
            # Process order event
            book.process_event(
                ev.order_number,
                int(ev.activity_type),
                ev.buy_sell,
                float(ev.limit_price),
                int(ev.volume_original)
            )
        elif event_kind == 2:
            # Process trade execution (remove filled qty from both buy and sell orders)
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
                snap["trade_date"] = str(ev.txn_datetime)[:10]
                snap["timestamp"] = ev.txn_datetime
                snap["seconds_from_1500"] = sec_from_1500
                snap["triggering_event"] = ev.activity_label
                snapshots.append(snap)

    if snapshots:
        os.makedirs(out_dir, exist_ok=True)
        df_snap = pd.DataFrame(snapshots)
        df_snap.to_parquet(out_file, index=False)
        print(f"[CLOB DONE] {symbol} date={date_str}: {len(df_snap)} snapshots.")
