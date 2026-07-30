"""
clob_builder.py — Replay orders for a (symbol, date) pair and emit CLOB snapshots.
"""
import os
import pandas as pd
from config.settings import ENRICHED_DATA_DIR, CLOB_DATA_DIR, SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
from stage4_clob.order_book import OrderBook

def build_clob_for_symbol_date(symbol, date_str):
    """
    Replay orders for symbol and date_str, emitting 1-second snapshots during settlement window.
    """
    out_dir = os.path.join(CLOB_DATA_DIR, symbol, f"date={date_str}")
    out_file = os.path.join(out_dir, "snapshots.parquet")
    if os.path.exists(out_file):
        return

    orders_path = os.path.join(ENRICHED_DATA_DIR, "cash_orders")
    trades_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")

    if not os.path.exists(orders_path) or not os.path.exists(trades_path):
        return

    # Load orders and trades for this date & symbol using PyArrow filters
    try:
        df_orders = pd.read_parquet(
            orders_path,
            filters=[("symbol", "==", symbol)]
        )
        df_trades = pd.read_parquet(
            trades_path,
            filters=[("symbol", "==", symbol)]
        )
    except Exception as e:
        return

    if df_orders.empty:
        return

    # Ensure sorting by txn_time_jiffies
    df_orders = df_orders.sort_values("txn_time_jiffies")

    book = OrderBook()
    snapshots = []

    # Map trades by buy/sell order numbers for execution tracking
    trade_buy_map = {}
    trade_sell_map = {}
    if not df_trades.empty:
        for _, tr in df_trades.iterrows():
            trade_buy_map[tr["buy_order_number"]] = trade_buy_map.get(tr["buy_order_number"], 0) + tr["trade_quantity"]
            trade_sell_map[tr["sell_order_number"]] = trade_sell_map.get(tr["sell_order_number"], 0) + tr["trade_quantity"]

    last_snap_second = -1

    for _, row in df_orders.iterrows():
        order_num = row["order_number"]
        act_type = row["activity_type"]
        side = row["buy_sell"]
        price = row["limit_price"]
        qty = row["volume_original"]
        t_time = row["trade_time"]

        # Process order event
        book.process_event(order_num, act_type, side, price, qty)

        # Check if trade filled order
        if order_num in trade_buy_map:
            book.remove_traded_qty(order_num, trade_buy_map.pop(order_num))
        if order_num in trade_sell_map:
            book.remove_traded_qty(order_num, trade_sell_map.pop(order_num))

        # Check if in settlement window (15:00:00 to 15:30:00)
        if SETTLEMENT_WINDOW_START <= t_time <= SETTLEMENT_WINDOW_END:
            # Parse seconds from 15:00
            h, m, s = map(int, t_time.split(":"))
            sec_from_1500 = (h - 15) * 3600 + m * 60 + s

            if sec_from_1500 != last_snap_second:
                last_snap_second = sec_from_1500
                snap = book.snapshot(depth=10)
                snap["symbol"] = symbol
                snap["trade_date"] = row["trade_date"]
                snap["timestamp"] = row["txn_datetime"]
                snap["seconds_from_1500"] = sec_from_1500
                snap["triggering_event"] = row["activity_label"]
                snapshots.append(snap)

    if snapshots:
        os.makedirs(out_dir, exist_ok=True)
        df_snap = pd.DataFrame(snapshots)
        df_snap.to_parquet(out_file, index=False)
        print(f"[CLOB DONE] {symbol} date={date_str}: {len(df_snap)} snapshots.")
