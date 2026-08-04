"""NSE Historical Tick Data fixed-width record layout definitions."""

from typing import List, Tuple

FieldSchema = Tuple[str, int, int, str]

# CM (Cash) Orders Layout (87 bytes + LF)
CM_ORDERS_SCHEMA: List[FieldSchema] = [
    ("record_indicator",   0,  2, "str"),
    ("segment",            2,  4, "str"),
    ("order_number",       6, 16, "long"),
    ("txn_time_jiffies",  22, 14, "long"),
    ("buy_sell",          36,  1, "str"),
    ("activity_type",     37,  1, "int"),
    ("symbol",            38, 10, "str"),
    ("series",            48,  2, "str"),
    ("volume_disclosed",  50,  8, "long"),
    ("volume_original",   58,  8, "long"),
    ("limit_price",       66,  8, "long"),
    ("trigger_price",     74,  8, "long"),
    ("mkt_order_flag",    82,  1, "str"),
    ("stop_loss_flag",    83,  1, "str"),
    ("ioc_flag",          84,  1, "str"),
    ("algo_indicator",    85,  1, "int"),
    ("client_identity",   86,  1, "int"),
]
CM_ORDERS_RECORD_LENGTH = 87

# CM (Cash) Trades Layout (100 bytes + LF)
CM_TRADES_SCHEMA: List[FieldSchema] = [
    ("record_indicator",       0,  2, "str"),
    ("segment",                2,  4, "str"),
    ("trade_number",           6, 16, "long"),
    ("txn_time_jiffies",      22, 14, "long"),
    ("symbol",                36, 10, "str"),
    ("series",                46,  2, "str"),
    ("trade_price",           48,  8, "long"),
    ("trade_quantity",        56,  8, "long"),
    ("buy_order_number",      64, 16, "long"),
    ("buy_algo_indicator",    80,  1, "int"),
    ("buy_client_identity",   81,  1, "int"),
    ("sell_order_number",     82, 16, "long"),
    ("sell_algo_indicator",   98,  1, "int"),
    ("sell_client_identity",  99,  1, "int"),
]
CM_TRADES_RECORD_LENGTH = 100

# FAO (Futures & Options) Orders Layout (112 bytes + LF)
FAO_ORDERS_SCHEMA: List[FieldSchema] = [
    ("record_indicator",   0,  2, "str"),
    ("segment",            2,  4, "str"),
    ("order_number",       6, 16, "long"),
    ("txn_time_jiffies",  22, 14, "long"),
    ("buy_sell",          36,  1, "str"),
    ("activity_type",     37,  1, "int"),
    ("symbol",            38, 10, "str"),
    ("instrument",        48,  6, "str"),
    ("expiry_date",       54,  9, "str"),
    ("strike_price",      63,  8, "long"),
    ("option_type",       71,  2, "str"),
    ("volume_disclosed",  73,  8, "long"),
    ("volume_original",   81,  8, "long"),
    ("limit_price",       89,  8, "long"),
    ("trigger_price",     97,  8, "long"),
    ("mkt_order_flag",   105,  1, "str"),
    ("stop_loss_flag",   106,  1, "str"),
    ("ioc_flag",         107,  1, "str"),
    ("spread_type",      108,  1, "str"),
    ("algo_indicator",   109,  1, "int"),
    ("client_identity",  110,  1, "int"),
    ("limit_price_ind",  111,  1, "str"),
]
FAO_ORDERS_RECORD_LENGTH = 112

# FAO (Futures & Options) Trades Layout (124 bytes + LF)
FAO_TRADES_SCHEMA: List[FieldSchema] = [
    ("record_indicator",       0,  2, "str"),
    ("segment",                2,  4, "str"),
    ("trade_number",           6, 17, "long"),
    ("txn_time_jiffies",      23, 14, "long"),
    ("symbol",                37, 10, "str"),
    ("instrument",            47,  6, "str"),
    ("expiry_date",           53,  9, "str"),
    ("strike_price",          62,  8, "long"),
    ("option_type",           70,  2, "str"),
    ("trade_price",           72,  8, "long"),
    ("trade_quantity",        80,  8, "long"),
    ("buy_order_number",      88, 16, "long"),
    ("buy_algo_indicator",   104,  1, "int"),
    ("buy_client_identity",  105,  1, "int"),
    ("sell_order_number",    106, 16, "long"),
    ("sell_algo_indicator",  122,  1, "int"),
    ("sell_client_identity", 123,  1, "int"),
]
FAO_TRADES_RECORD_LENGTH = 124
