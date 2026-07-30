"""
clob_schemas.py — PyArrow/Pandas schema for CLOB snapshots.
"""

CLOB_SNAPSHOT_FIELDS = [
    "symbol", "trade_date", "timestamp", "seconds_from_1500",
    "best_bid", "best_ask", "midpoint", "spread", "spread_bps",
    "total_bid_volume", "total_ask_volume", "book_imbalance",
    "triggering_event"
] + [f"bid_depth_{i}" for i in range(1, 11)] + [f"ask_depth_{i}" for i in range(1, 11)]
