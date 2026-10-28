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
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATA_ROOT, EXPIRY_CONTROL_PAIRS, RESULTS_DIR  # noqa: E402

# One link per F&O file across the library's shares, to the copy whose size matches its .trg
# record where there is more than one (see scripts/fao_links.py).
FAO_LINKS = Path.home() / "sandbox/data/raw/fao_all"
OUT_DIR = Path(RESULTS_DIR) / "futures_book"
SCRATCH = Path(DATA_ROOT) / "tmp" / "futures_book"
CASH_BOOKS = Path.home() / "sandbox/BlockCrosser/data/clob_snapshots"

# Expiry session -> (control session, contract code as the file writes it, e.g. 27Jan2022).
PAIRS = {e: (c, pd.Timestamp(f"{e[4:]}-{e[2:4]}-{e[:2]}").strftime("%d%b%Y"))
         for e, c in EXPIRY_CONTROL_PAIRS}
LEVELS = 5
OPEN, CLOSE = 9 * 3600 + 15 * 60, 15 * 3600 + 30 * 60


def derivative_symbols() -> List[str]:
    universe = json.loads((PROJECT_ROOT / "config" / "universe_2022.json").read_text())
    return sorted(universe["groups"]["liquid"] + universe["groups"]["illiquid"])


def order_parts(session: str) -> List[Path]:
    """Every part of the session's order file, one per part number."""
    return sorted(FAO_LINKS.glob(f"FAO_Orders_{session}_*.DAT.gz"))


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
                  partition_by="symbol", threads=8)
    return str(out)


def parse_orders(session: str, contract: str, symbols: List[str]) -> Path:
    """Parsed orders of the expiring futures, one partition per symbol."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    work = SCRATCH / session
    done = work / "parsed.ok"
    if not done.exists():
        # Reading the share is most of the cost, so a parse that finished is kept.
        shutil.rmtree(work, ignore_errors=True)
        parts = [p for p in order_parts(session) if carries_stock_futures(p)]
        print(f"{session}: stock futures in {[p.name for p in parts]}", flush=True)
        jobs = [(p, work / f"part={p.name.split('_')[-1][:2]}", contract, symbols)
                for p in parts]
        # One part at a time: the share delivers less in total to concurrent readers.
        # The parts split the stream by security, not by time, so a part whose download is
        # incomplete loses only its own securities for the session; it is skipped and named.
        for job in jobs:
            try:
                _parse_part(job)
            except ValueError as exc:
                if "does not match" not in str(exc):
                    raise
                print(f"{session}: skipped incomplete {job[0].name}", flush=True)
        done.touch()
    # A symbol's orders belong to one stream, but the parts are combined and sorted in case
    # one is split, keeping the file order within a timestamp. Arrow rather than pandas, so
    # the column types the book replay expects are kept.
    merged = work / "orders"
    shutil.rmtree(merged, ignore_errors=True)
    for symbol in symbols:
        files = sorted(work.glob(f"part=*/**/symbol={symbol}/*.parquet"))
        if not files:
            continue
        table = pa.concat_tables([pq.read_table(f, partitioning=None) for f in files])
        if len(files) > 1:
            order = np.argsort(table.column("txn_time").to_numpy(), kind="stable")
            table = table.take(order)
        dest = merged / f"symbol={symbol}"
        dest.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, dest / "part-000.parquet")
    return merged


def reduce_book(frame: pd.DataFrame, scale: float = 1.0) -> pd.DataFrame:
    """Quoted spread (bps), displayed depth within five levels (crore) and realised variance
    of the mid (squared five-second log changes, bps squared) per minute.

    `scale` converts prices to rupees: the cash snapshots are already in rupees, the
    replayed futures books are in paise."""
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
            depth += np.nan_to_num(scale * px.to_numpy(float) * qty.to_numpy(float))
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
    day = f"{session[4:]}-{session[2:4]}-{session[:2]}"
    nsetick.build_books(input=str(orders), out=str(books), date=day, interval_secs=5.0,
                        levels=LEVELS, threads=8, symbols=present)
    rows = []
    for symbol in present:
        files = list(books.glob(f"**/symbol={symbol}/*.parquet"))
        if not files:
            continue
        r = reduce_book(pd.concat([pd.read_parquet(f) for f in files]), scale=0.01)
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
