"""Order books of the expiring stock futures on the order book sample's March-June sessions.

The derivatives order file is split into parts by stream, and the stock futures sit in a few
of them. For each session the parts that carry FUTSTK are found by reading their first rows,
parsed with the stock futures of the expiring month only (spread orders excluded), and the
book of each future is replayed into five-second snapshots. On the control session the same
contract has one day to run. Each snapshot is then reduced to the quoted spread and the
displayed depth per security and minute, and only that reduction is kept.

Output: data/results/futures_book/session=<DDMMYYYY>.parquet with one row per security and
minute, and the same reduction of the cash book for the same securities and sessions, so
that the two markets are measured identically.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATA_ROOT, RESULTS_DIR  # noqa: E402

FAO_ROOT = Path("/mnt/nse/FAO 2022")
OUT_DIR = Path(RESULTS_DIR) / "futures_book"
SCRATCH = Path(DATA_ROOT) / "tmp" / "futures_book"
CASH_BOOKS = Path.home() / "sandbox/BlockCrosser/data/clob_snapshots"

# Expiry session -> (control session, contract code as the file writes it).
PAIRS = {
    "31032022": ("30032022", "31Mar2022"),
    "28042022": ("27042022", "28Apr2022"),
    "26052022": ("25052022", "26May2022"),
    "30062022": ("29062022", "30Jun2022"),
}
LEVELS = 5
OPEN, CLOSE = 9 * 3600 + 15 * 60, 15 * 3600 + 30 * 60


def derivative_symbols() -> List[str]:
    universe = json.loads((PROJECT_ROOT / "config" / "universe_2022.json").read_text())
    return sorted(universe["groups"]["liquid"] + universe["groups"]["illiquid"])


def order_parts(session: str) -> List[Path]:
    """Every part of the session's order file, one per part number."""
    found = {}
    # The share is slow to walk recursively, so only the download folders are listed.
    for folder in sorted(FAO_ROOT.glob("*/NSEDownload/*/FAO")):
        for path in sorted(folder.glob(f"FAO_Orders_{session}_*.DAT.gz")):
            found.setdefault(path.name, path)
    return [found[k] for k in sorted(found)]


def carries_stock_futures(path: Path, rows: int = 2_000) -> bool:
    """Whether the part belongs to the stock derivatives stream (FUTSTK and OPTSTK)."""
    with gzip.open(path, "rt", errors="replace") as fh:
        for i, line in enumerate(fh):
            if line[48:54] in ("FUTSTK", "OPTSTK"):
                return True
            if i >= rows:
                return False
    return False


def _parse_part(args) -> str:
    import nsetick

    path, out, contract, symbols = args
    quoted = ", ".join(f"'{s}'" for s in symbols)
    nsetick.parse(input=str(path), out=str(out), layout="fao_orders",
                  where=(f"instrument == 'FUTSTK' and spread_type == '*' "
                         f"and expiry_date == '{contract}' and symbol in ({quoted})"),
                  partition_by="symbol", threads=4)
    return str(out)


def parse_orders(session: str, contract: str, symbols: List[str]) -> Path:
    """Parsed orders of the expiring futures, one partition per symbol."""
    work = SCRATCH / session
    shutil.rmtree(work, ignore_errors=True)
    parts = [p for p in order_parts(session) if carries_stock_futures(p)]
    print(f"{session}: stock futures in {[p.name for p in parts]}", flush=True)
    jobs = [(p, work / f"part={p.name.split('_')[-1][:2]}", contract, symbols) for p in parts]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        list(pool.map(_parse_part, jobs))
    # A symbol's orders belong to one stream, but the parts are combined and sorted in case
    # one is split, keeping the file order within a timestamp.
    merged = work / "orders"
    for symbol in symbols:
        files = sorted(work.glob(f"part=*/**/symbol={symbol}/*.parquet"))
        if not files:
            continue
        frame = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        frame = frame.sort_values(["txn_time"], kind="stable")
        dest = merged / f"symbol={symbol}"
        dest.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(dest / "data_0.parquet", index=False)
    return merged


def reduce_book(frame: pd.DataFrame) -> pd.DataFrame:
    """Quoted spread (bps), displayed depth within five levels (crore) and realised variance
    of the mid (squared five-second log changes, bps squared) per minute."""
    t = pd.to_datetime(frame.snapshot_time)
    sec = (t.dt.hour * 3600 + t.dt.minute * 60 + t.dt.second).to_numpy()
    bid, ask = frame.best_bid.to_numpy(float), frame.best_ask.to_numpy(float)
    ok = (sec >= OPEN) & (sec < CLOSE) & (bid > 0) & (ask > bid)
    if not ok.any():
        return pd.DataFrame()
    mid = (bid + ask) / 2.0
    depth = np.zeros(len(frame))
    for k in range(1, LEVELS + 1):
        for side in ("bid", "ask"):
            px, qty = frame.get(f"{side}_px_{k}"), frame.get(f"{side}_qty_{k}")
            if px is None or qty is None:
                continue
            depth += np.nan_to_num(px.to_numpy(float) * qty.to_numpy(float))
    logmid = 1e4 * np.log(np.where(ok, mid, np.nan))
    change2 = np.r_[np.nan, np.diff(logmid)] ** 2
    out = pd.DataFrame({
        "minute": ((sec - OPEN) // 60)[ok],
        "spread_bps": (1e4 * (ask - bid) / mid)[ok],
        "depth_cr": (depth / 1e7)[ok],
        "rv_bps2": change2[ok],
    })
    return out.groupby("minute").agg(spread_bps=("spread_bps", "mean"),
                                     depth_cr=("depth_cr", "mean"),
                                     rv_bps2=("rv_bps2", "sum")).reset_index()


def futures_session(session: str, contract: str, symbols: List[str]) -> pd.DataFrame:
    import nsetick

    orders = parse_orders(session, contract, symbols)
    books = SCRATCH / session / "books"
    present = sorted(p.name.split("=", 1)[1] for p in orders.glob("symbol=*"))
    nsetick.build_books(input=str(orders), out=str(books), interval_secs=5.0, levels=LEVELS,
                        threads=8, symbols=present)
    rows = []
    for symbol in present:
        files = list(books.glob(f"**/symbol={symbol}/*.parquet"))
        if not files:
            continue
        r = reduce_book(pd.concat([pd.read_parquet(f) for f in files]))
        if r.empty:
            continue
        r["symbol"] = symbol
        rows.append(r)
    shutil.rmtree(SCRATCH / session, ignore_errors=True)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out["market"] = "futures"
    return out


def cash_session(session: str, symbols: List[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        path = CASH_BOOKS / symbol / f"date={session}" / "snapshots.parquet"
        if not path.exists():
            continue
        cols = ["snapshot_time", "best_bid", "best_ask"] + [
            f"{s}_{f}_{k}" for k in range(1, LEVELS + 1) for s in ("bid", "ask")
            for f in ("px", "qty")]
        r = reduce_book(pd.read_parquet(path, columns=cols))
        if r.empty:
            continue
        r["symbol"] = symbol
        rows.append(r)
    out = pd.concat(rows, ignore_index=True)
    out["market"] = "cash"
    return out


def main() -> None:
    symbols = derivative_symbols()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for expiry, (control, contract) in PAIRS.items():
        for session in (expiry, control):
            dest = OUT_DIR / f"session={session}.parquet"
            if dest.exists():
                continue
            started = time.time()
            fut = futures_session(session, contract, symbols)
            cash = cash_session(session, symbols)
            frame = pd.concat([fut, cash], ignore_index=True)
            frame["session"] = session
            frame["is_expiry"] = session == expiry
            frame.to_parquet(dest, index=False)
            print(f"{session}: {fut.symbol.nunique()} futures, {cash.symbol.nunique()} cash, "
                  f"{time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
