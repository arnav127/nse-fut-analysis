"""Quoted spread, displayed depth and volatility of the cash book through the whole session.

For every security of the universe and every session of the order book sample, the
five-second snapshots are reduced to one row per minute (see futures_book.reduce_book). The
result shows whether the cost of trading rises only in the settlement window or across the
expiry day.

Output: data/results/book_profile.parquet.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (CONTROL_DAYS_DDMMYYYY, EXPIRY_THURSDAYS_DDMMYYYY,  # noqa: E402
                             RESULTS_DIR)
from stage9_tape.futures_book import CASH_BOOKS, LEVELS, reduce_book  # noqa: E402


def _one(args) -> pd.DataFrame:
    symbol, session = args
    path = CASH_BOOKS / symbol / f"date={session}" / "snapshots.parquet"
    if not path.exists():
        return pd.DataFrame()
    cols = ["snapshot_time", "best_bid", "best_ask"] + [
        f"{s}_{f}_{k}" for k in range(1, LEVELS + 1) for s in ("bid", "ask") for f in ("px", "qty")]
    out = reduce_book(pd.read_parquet(path, columns=cols))
    out["symbol"], out["session"] = symbol, session
    return out


def main() -> None:
    universe = json.loads((PROJECT_ROOT / "config" / "universe_2022.json").read_text())
    group = {s: g for g, members in universe["groups"].items() for s in members}
    sessions = EXPIRY_THURSDAYS_DDMMYYYY + CONTROL_DAYS_DDMMYYYY
    jobs = [(s, d) for s in group for d in sessions]
    with ProcessPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(_one, jobs, chunksize=20))
    frame = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    frame["group"] = frame.symbol.map(group)
    frame["is_expiry"] = frame.session.isin(EXPIRY_THURSDAYS_DDMMYYYY)
    frame.to_parquet(Path(RESULTS_DIR) / "book_profile.parquet", index=False)
    print(f"{len(frame):,} security-minutes, {frame.symbol.nunique()} securities, "
          f"{frame.session.nunique()} sessions")


if __name__ == "__main__":
    main()
