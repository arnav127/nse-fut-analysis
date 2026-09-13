"""Derive the study universe from the tape rather than from a present-day index.

Membership taken from today's index is the defect this exists to avoid: a security listed
in 2023, or renamed since, or added to the index after a run-up, is not a 2022 security.
Average daily traded value measured from the sessions actually being studied is
contemporaneous by construction, reproducible offline, and auditable.

It is also the better variable. The question is what it costs to move a security's closing
half-hour, and that is an execution question - how much can trade without moving the price -
which is what ADV measures directly and market capitalisation only proxies.

Requires a full-cross-section parse:

    python run_all.py --stage parse --parse-all-eq

which keeps every EQ symbol rather than only the configured universe. Derivatives
eligibility cannot be read off the cash tape, so it comes from a file:

    config/fo_underlyings_2022.txt   one symbol per line

NSE publishes the list of F&O underlyings. Without it the groups are formed on ADV alone
and the output records `fo_verified: false`, which the manuscript then reports - a universe
whose derivatives eligibility is assumed is still usable, but the reader has to be told.

Writes config/universe_2022.json, which config/universe.py loads in preference to its
fallback lists.

    python scripts/build_universe.py [--group-size 20] [--min-trades 500]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from config.settings import ALL_TARGET_DATES, PARSED_DATA_DIR  # noqa: E402
from config.universe import DERIVED_PATH, GROUP_SIZE  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.paths import parsed_dir  # noqa: E402

logger = setup_logger("Universe", "universe.log")
FO_LIST = PROJECT_ROOT / "config" / "fo_underlyings_2022.txt"


def load_fo_underlyings() -> Optional[Set[str]]:
    if not FO_LIST.exists():
        return None
    symbols = {line.strip().upper() for line in FO_LIST.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")}
    return symbols or None


def traded_value() -> pd.DataFrame:
    """Per-symbol turnover and trade count across every parsed session."""
    patterns = []
    for session in ALL_TARGET_DATES:
        directory = parsed_dir("cash_trades", session)
        if any(directory.glob("symbol=*")):
            patterns.append((directory / "symbol=*" / "*.parquet").as_posix())
    if not patterns:
        raise SystemExit("no parsed trade data found; run the parse stage first")

    logger.info(f"[UNIVERSE] measuring turnover across {len(patterns)} sessions")
    union = " UNION ALL ".join(
        f"SELECT symbol, trade_price, trade_quantity, record_indicator "
        f"FROM read_parquet('{p}', hive_partitioning = true)" for p in patterns)

    with duckdb.connect() as conn:
        return conn.execute(f"""
            SELECT
                symbol,
                COUNT(*) AS trades,
                SUM(CAST(trade_quantity AS DOUBLE)) AS shares,
                -- Prices are integer paise at this stage; turnover in crore.
                SUM(CAST(trade_price AS DOUBLE) / 100.0 * trade_quantity) / 1e7 AS turnover_cr,
                COUNT(DISTINCT CAST(txn_time AS DATE)) AS sessions_present
            FROM ({union})
            WHERE record_indicator = 'RM'
            GROUP BY symbol
        """.replace("COUNT(DISTINCT CAST(txn_time AS DATE))", "0")).df()


def _sessions_present() -> pd.Series:
    """How many of the studied sessions each symbol actually traded in.

    Counted from the partition directories rather than from the rows: a symbol present in a
    session has a partition, and counting directories avoids a second pass over the data.
    """
    counts: dict[str, int] = {}
    for session in ALL_TARGET_DATES:
        for part in parsed_dir("cash_trades", session).glob("symbol=*"):
            symbol = part.name.split("=", 1)[1]
            counts[symbol] = counts.get(symbol, 0) + 1
    return pd.Series(counts, name="sessions_present")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-size", type=int, default=GROUP_SIZE)
    parser.add_argument("--min-trades", type=float, default=500.0,
                        help="minimum mean trades per session for a symbol to be eligible")
    args = parser.parse_args()

    frame = traded_value()
    present = _sessions_present()
    frame["sessions_present"] = frame.symbol.map(present).fillna(0).astype(int)
    n_sessions = int(frame.sessions_present.max())

    # Present in every session. A security that stopped trading mid-year cannot contribute a
    # matched expiry-control pair for the months it is absent, and letting it into the
    # universe would make the group means depend on which months each member appeared in.
    universe = frame[frame.sessions_present == n_sessions].copy()
    universe["trades_per_session"] = universe.trades / n_sessions
    universe["adv_cr"] = universe.turnover_cr / n_sessions

    # The activity floor is a measurement criterion, not a size cut-off. Below a few hundred
    # trades a session, a one-second book snapshot sees nothing happen between consecutive
    # observations and the microstructure measures are not identified rather than merely
    # small.
    eligible = universe[universe.trades_per_session >= args.min_trades].copy()
    eligible = eligible.sort_values("adv_cr", ascending=False).reset_index(drop=True)

    fo = load_fo_underlyings()
    fo_verified = fo is not None
    if fo_verified:
        derivative = eligible[eligible.symbol.isin(fo)]
        cash_only = eligible[~eligible.symbol.isin(fo)]
        logger.info(f"[UNIVERSE] {len(derivative)} of {len(eligible)} eligible symbols are "
                    f"derivatives underlyings")
    else:
        logger.warning(
            f"[UNIVERSE] {FO_LIST.name} not found. Groups will be formed on turnover alone "
            f"and the placebo group cannot be guaranteed free of derivatives underlyings; "
            f"the manuscript will report the universe as unverified.")
        derivative = eligible
        cash_only = eligible.iloc[0:0]

    size = args.group_size
    if len(derivative) < 2 * size:
        raise SystemExit(f"only {len(derivative)} eligible derivative underlyings; need "
                         f"{2 * size} for two groups of {size}")

    liquid = derivative.head(size).symbol.tolist()
    illiquid = derivative.tail(size).symbol.tolist()

    # The placebo group is matched on turnover to the illiquid group rather than taken from
    # the bottom of the list. A placebo of near-untraded shells would differ from the
    # treatment groups in every respect, not only in whether a contract expires on them, and
    # would therefore rule nothing out.
    placebo: List[str] = []
    if len(cash_only):
        target = derivative.tail(size).adv_cr.median()
        placebo = (cash_only.assign(distance=(cash_only.adv_cr - target).abs())
                   .nsmallest(size, "distance").symbol.tolist())

    payload = {
        "method": "average daily traded value measured from the studied sessions",
        "sessions": n_sessions,
        "min_trades_per_session": args.min_trades,
        "group_size": size,
        "fo_verified": fo_verified,
        "eligible_symbols": len(eligible),
        "groups": {"liquid": liquid, "illiquid": illiquid, "placebo": placebo},
        "adv_cr": {row.symbol: round(row.adv_cr, 3) for row in eligible.itertuples()
                   if row.symbol in set(liquid) | set(illiquid) | set(placebo)},
    }
    DERIVED_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    eligible.to_csv(PROJECT_ROOT / "config" / "universe_2022_adv.csv", index=False)

    print(f"sessions            : {n_sessions}")
    print(f"eligible symbols    : {len(eligible):,}")
    print(f"derivatives verified: {fo_verified}")
    for name, members in payload["groups"].items():
        if not members:
            print(f"{name:20s}: (empty)")
            continue
        advs = [payload['adv_cr'][s] for s in members]
        print(f"{name:20s}: {len(members)} symbols, ADV {min(advs):,.1f}-{max(advs):,.1f} cr")
    print(f"\nwrote {DERIVED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
