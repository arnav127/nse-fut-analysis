"""Nifty 50 index futures and options trades on the order book sample's sessions.

Only the parts of the F&O trade file that carry index derivatives are read, and only NIFTY
contracts are kept. Each session is then reduced to what the hedge-unwinding question needs,
by participant category and contract type: volume and net aggressor flow, in the settlement
window and over the session, and option volume by moneyness (strike relative to the index).

Output: data/results/s14_index_deriv.parquet. Run on the HPC; reads data/raw/fao_all.
"""

from __future__ import annotations

import gzip
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATA_ROOT, EXPIRY_CONTROL_PAIRS, RESULTS_DIR  # noqa: E402

LINKS = Path.home() / "sandbox/data/raw/fao_all"
SCRATCH = Path(DATA_ROOT) / "tmp" / "index_deriv"


def index_parts(session: str):
    parts = []
    for path in sorted(LINKS.glob(f"FAO_Trades_{session}_*.DAT.gz")):
        with gzip.open(path, "rt", errors="replace") as fh:
            head = [next(fh, "") for _ in range(200)]
        if any(line[47:53] in ("FUTIDX", "OPTIDX") for line in head):
            parts.append(path)
    return parts


def one_session(session: str) -> pd.DataFrame:
    import duckdb
    import nsetick

    work = SCRATCH / session
    shutil.rmtree(work, ignore_errors=True)
    for i, part in enumerate(index_parts(session)):
        try:
            nsetick.parse(input=str(part), out=str(work / f"p{i}"), layout="fao_trades",
                          where="symbol == 'NIFTY' and instrument in ('FUTIDX', 'OPTIDX')",
                          threads=3)
        except ValueError as exc:
            print(f"{session}: skipped {part.name}: {exc}", flush=True)
    files = [p.as_posix() for p in work.rglob("*.parquet")]
    if not files:
        return pd.DataFrame()
    con = duckdb.connect()
    frame = con.execute(f"""
        WITH t AS (
            SELECT instrument, option_type, expiry_date,
                   CAST(strike_price AS DOUBLE) / 100.0 AS strike,
                   CAST(trade_price AS DOUBLE) / 100.0 AS px,
                   CAST(trade_quantity AS DOUBLE) AS q,
                   CAST(txn_time AS TIME) AS tt,
                   CASE WHEN buy_order_number > sell_order_number THEN 1.0 ELSE -1.0 END AS sgn,
                   CASE WHEN buy_order_number > sell_order_number THEN buy_client_identity
                        ELSE sell_client_identity END AS aggressor,
                   buy_client_identity AS buyer, sell_client_identity AS seller
            FROM read_parquet({files})
            WHERE record_indicator = 'RM' AND trade_quantity > 0
        ),
        near AS (SELECT MIN(expiry_date) AS e FROM t)
        SELECT instrument, option_type, (expiry_date = (SELECT e FROM near)) AS expiring,
               (tt >= TIME '15:00:00' AND tt <= TIME '15:30:00') AS in_window,
               aggressor, round(strike / 50) * 50 AS strike50,
               SUM(q) AS volume, SUM(sgn * q) AS net_aggressor,
               SUM(q * (CASE WHEN buyer = 2 THEN 1 ELSE 0 END)
                   - q * (CASE WHEN seller = 2 THEN 1 ELSE 0 END)) AS prop_net,
               SUM(q * (CASE WHEN buyer = 1 THEN 1 ELSE 0 END)
                   - q * (CASE WHEN seller = 1 THEN 1 ELSE 0 END)) AS custodian_net,
               SUM(px * q) / SUM(q) AS vwap, COUNT(*) AS trades
        FROM t GROUP BY ALL
    """).df()
    frame["session"] = session
    shutil.rmtree(work, ignore_errors=True)
    return frame


def main() -> None:
    out = Path(RESULTS_DIR) / "s14_index_deriv"
    out.mkdir(parents=True, exist_ok=True)
    # Expiry and control in turn, so that whatever finishes comes in complete pairs.
    order = [s for pair in EXPIRY_CONTROL_PAIRS for s in pair]
    todo = [s for s in order if not (out / f"{s}.parquet").exists()]
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(one_session, s): s for s in todo}
        for future in as_completed(futures):
            session = futures[future]
            future.result().to_parquet(out / f"{session}.parquet", index=False)
            print(session, flush=True)


if __name__ == "__main__":
    main()
