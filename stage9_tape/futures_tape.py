"""Trading in the stock futures on the expiry and control sessions of March to June.

For each security and session, and separately for the expiring contract and the next one:
volume, the share of the session's volume traded in the settlement window, the order
imbalance (BI - SI) / (BI + SI) over the window, and the move from the window's first minute
to its last. The aggressor is the side whose order arrived later, as in the cash market.

Output: data/results/s12_futures_tape.csv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (RESULTS_DIR, SETTLEMENT_WINDOW_END,  # noqa: E402
                             SETTLEMENT_WINDOW_START)
from stage9_tape.futures_book import PAIRS  # noqa: E402
from utils.duck import connect  # noqa: E402
from utils.paths import parsed_dir  # noqa: E402


def reduce_session(conn, session: str, symbols) -> pd.DataFrame:
    pattern = (parsed_dir("fao_trades", session) / "symbol=*" / "*.parquet").as_posix()
    quoted = ", ".join(f"'{s}'" for s in symbols)
    start, end = SETTLEMENT_WINDOW_START, SETTLEMENT_WINDOW_END
    window = f"tt >= TIME '{start}' AND tt <= TIME '{end}'"
    first = f"tt >= TIME '{start}' AND tt < TIME '{start}' + INTERVAL 1 MINUTE"
    last = f"tt >= TIME '{end}' - INTERVAL 1 MINUTE AND tt <= TIME '{end}'"
    return conn.execute(f"""
        WITH f AS (
            SELECT symbol, expiry_date, CAST(txn_time AS TIME) AS tt,
                   CAST(trade_price AS DOUBLE) / 100.0 AS px,
                   CAST(trade_quantity AS DOUBLE) AS q,
                   CASE WHEN buy_order_number > sell_order_number THEN 1.0 ELSE -1.0 END AS sgn
            FROM read_parquet('{pattern}', hive_partitioning = true)
            WHERE instrument = 'FUTSTK' AND record_indicator = 'RM' AND trade_quantity > 0
              AND symbol IN ({quoted})
        ),
        ranked AS (
            SELECT *, DENSE_RANK() OVER (PARTITION BY symbol ORDER BY expiry_date) AS contract
            FROM f
        )
        SELECT symbol, contract, any_value(expiry_date) AS expiry_date,
               SUM(q) AS volume,
               SUM(q) FILTER (WHERE {window}) AS window_volume,
               SUM(q) FILTER (WHERE {window} AND sgn > 0) AS window_bi,
               SUM(q) FILTER (WHERE {window} AND sgn < 0) AS window_si,
               SUM(px * q) FILTER (WHERE {first}) / NULLIF(SUM(q) FILTER (WHERE {first}), 0)
                   AS first1_vwap,
               SUM(px * q) FILTER (WHERE {last}) / NULLIF(SUM(q) FILTER (WHERE {last}), 0)
                   AS last1_vwap
        FROM ranked WHERE contract <= 2
        GROUP BY symbol, contract
    """).df()


def main() -> None:
    universe = json.loads((PROJECT_ROOT / "config" / "universe_2022.json").read_text())
    group = {s: g for g in ("liquid", "illiquid") for s in universe["groups"][g]}
    frames = []
    with connect() as conn:
        for expiry, (control, _) in PAIRS.items():
            for session in (expiry, control):
                frame = reduce_session(conn, session, sorted(group))
                frame["session"], frame["is_expiry"] = session, session == expiry
                frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    out["group"] = out.symbol.map(group)
    out["contract"] = out.contract.map({1: "near", 2: "next"})
    out.to_csv(Path(RESULTS_DIR) / "s12_futures_tape.csv", index=False)
    print(out.groupby(["is_expiry", "contract"])[["volume", "window_volume"]].sum())


if __name__ == "__main__":
    main()
