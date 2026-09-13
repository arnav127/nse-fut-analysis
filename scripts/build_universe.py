"""Select the securities studied, from the tape.

Three groups:

  liquid      most traded derivatives underlyings
  illiquid    least traded derivatives underlyings
  placebo     securities with no derivative, matched to the illiquid group

The first two carry the same settlement incentive and differ in what it costs to act on it.
The third carries no incentive at all, so any expiry-Thursday effect there belongs to the
calendar - month-end flows, index rebalancing, index option expiry - rather than to the
settlement mechanism. Without it every result in the report is open to that explanation.

Four things this gets right that a hand-picked list does not.

**Membership is contemporaneous.** Ranking is computed from the sessions actually studied,
not from a present-day index. A security listed in 2023, renamed since, or added to an index
after a run-up is not a 2022 security, and taking membership from today's index silently
mixes all three into a 2022 sample.

**Ranking uses control sessions only.** Turnover on an expiry Thursday is partly the thing
being measured. Assigning a security to the liquid or illiquid group using its expiry-day
activity would make the grouping a function of the outcome, and any difference between the
groups would then be partly mechanical. Only the twelve control sessions are used.

**Placebo securities are matched on turnover and on price.** Matching on turnover alone is
not enough: quoted spread in basis points depends on the tick size relative to the price, so
a placebo group of systematically cheaper shares would show wider spreads for a reason that
has nothing to do with expiry. Matching is nearest-neighbour without replacement on both.

**Membership has to be stable.** A security whose turnover rank swings across the year is
not reliably liquid or illiquid, and including it puts a security in one group that belonged
in the other for part of the sample.

Requires a full cross-section parse:

    python run_all.py --stage parse --parse-all-eq

and, for the placebo group, the list of derivatives underlyings:

    config/fo_underlyings_2022.txt     one symbol per line

NSE publishes this. Without it the script builds the two derivative groups by turnover alone,
records `fo_verified: false`, and produces no placebo group - which the report then states,
because a universe whose derivatives eligibility is assumed is usable only if the reader is
told.

    python scripts/build_universe.py [--group-size 50] [--min-trades 250]
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
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config.settings import (  # noqa: E402
    ALL_TARGET_DATES,
    CONTROL_DAYS_DDMMYYYY,
    EXPIRY_THURSDAYS_DDMMYYYY,
)
from config.universe import DERIVED_PATH, GROUP_SIZE  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.paths import parsed_dir, session_to_iso  # noqa: E402

logger = setup_logger("Universe", "universe.log")
CONFIG_DIR = PROJECT_ROOT / "config"
FO_LIST = CONFIG_DIR / "fo_underlyings_2022.txt"

# A security whose monthly turnover rank spans more than this fraction of the cross-section
# is not reliably in either group. Loose enough to keep a name that drifted, tight enough to
# drop one that was in the top decile one month and the bottom half the next.
MAX_RANK_SPAN = 0.35


def load_fo_underlyings() -> Optional[Set[str]]:
    if not FO_LIST.exists():
        return None
    symbols = {line.strip().upper().split(",")[0]
               for line in FO_LIST.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.lstrip().startswith("#")}
    return symbols or None


def session_statistics() -> pd.DataFrame:
    """Turnover, trade count and mean price for every symbol in every parsed session."""
    parts = []
    for session in ALL_TARGET_DATES:
        directory = parsed_dir("cash_trades", session)
        if not any(directory.glob("symbol=*")):
            continue
        pattern = (directory / "symbol=*" / "*.parquet").as_posix()
        parts.append(f"""
            SELECT '{session}' AS session, symbol,
                   COUNT(*) AS trades,
                   SUM(CAST(trade_quantity AS DOUBLE)) AS shares,
                   SUM(CAST(trade_price AS DOUBLE) / 100.0 * trade_quantity) AS turnover_inr
            FROM read_parquet('{pattern}', hive_partitioning = true)
            WHERE record_indicator = 'RM'
            GROUP BY symbol""")
    if not parts:
        raise SystemExit("no parsed trade data; run: python run_all.py --stage parse --parse-all-eq")

    logger.info(f"[UNIVERSE] measuring {len(parts)} sessions")
    with duckdb.connect() as conn:
        frame = conn.execute(" UNION ALL ".join(parts)).df()
    frame["mean_price"] = frame.turnover_inr / frame.shares.replace(0, np.nan)
    return frame


def _rank_stability(per_session: pd.DataFrame) -> pd.DataFrame:
    """Spread of each symbol's within-session turnover rank, as a fraction of the field."""
    ranked = per_session.copy()
    ranked["pct_rank"] = ranked.groupby("session").turnover_inr.rank(pct=True, ascending=False)
    span = ranked.groupby("symbol").pct_rank.agg(
        rank_median="median",
        # Interdecile rather than full range: one quiet session should not disqualify a
        # security that is otherwise consistent.
        rank_span=lambda s: float(s.quantile(0.9) - s.quantile(0.1)))
    return span.reset_index()


def _match_placebo(candidates: pd.DataFrame, targets: pd.DataFrame, size: int) -> List[str]:
    """Nearest-neighbour match on log turnover and log price, without replacement.

    Both in logs, because both span orders of magnitude and a difference of a factor of two
    matters equally at either end of the range. Without replacement, because reusing one
    security as the match for several targets would make the placebo group narrower than the
    group it is standing in for.
    """
    if candidates.empty or targets.empty:
        return []

    pool = candidates.copy()
    pool["log_adv"] = np.log(pool.adv_inr.clip(lower=1.0))
    pool["log_price"] = np.log(pool.mean_price.clip(lower=1.0))
    goal = targets.assign(log_adv=np.log(targets.adv_inr.clip(lower=1.0)),
                          log_price=np.log(targets.mean_price.clip(lower=1.0)))

    # Standardised so neither dimension dominates the distance by having a wider range.
    scale_adv = pool.log_adv.std() or 1.0
    scale_price = pool.log_price.std() or 1.0

    chosen: List[str] = []
    used: Set[str] = set()
    for target in goal.sort_values("adv_inr", ascending=False).itertuples():
        remaining = pool[~pool.symbol.isin(used)]
        if remaining.empty:
            break
        distance = np.hypot((remaining.log_adv - target.log_adv) / scale_adv,
                            (remaining.log_price - target.log_price) / scale_price)
        pick = remaining.loc[distance.idxmin()]
        chosen.append(pick.symbol)
        used.add(pick.symbol)
        if len(chosen) >= size:
            break
    return chosen


def _balance(frame: pd.DataFrame, members: dict) -> pd.DataFrame:
    """How alike the groups are on the variables the matching was meant to equalise."""
    rows = []
    for group, symbols in members.items():
        if not symbols:
            continue
        block = frame[frame.symbol.isin(symbols)]
        rows.append({
            "group": group,
            "n": len(block),
            "adv_cr_median": block.adv_inr.median() / 1e7,
            "adv_cr_min": block.adv_inr.min() / 1e7,
            "adv_cr_max": block.adv_inr.max() / 1e7,
            "price_median": block.mean_price.median(),
            "trades_per_session_median": block.trades_per_session.median(),
        })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select the study universe from the tape")
    parser.add_argument("--group-size", type=int, default=GROUP_SIZE)
    parser.add_argument("--min-trades", type=float, default=250.0,
                        help="minimum median trades per control session")
    parser.add_argument("--max-rank-span", type=float, default=MAX_RANK_SPAN)
    args = parser.parse_args()

    per_session = session_statistics()
    sessions_seen = sorted(per_session.session.unique())
    control_sessions = [s for s in CONTROL_DAYS_DDMMYYYY if s in sessions_seen]
    expiry_sessions = [s for s in EXPIRY_THURSDAYS_DDMMYYYY if s in sessions_seen]
    if not control_sessions:
        raise SystemExit("no control sessions parsed; ranking needs them")

    # Present in every session. A security absent for a month cannot contribute a matched
    # pair for that month, and letting it in would make each group's mean depend on which
    # months its members happened to trade in.
    presence = per_session.groupby("symbol").session.nunique()
    complete = set(presence[presence == len(sessions_seen)].index)

    control = per_session[per_session.session.isin(control_sessions)]
    stats = control.groupby("symbol").agg(
        adv_inr=("turnover_inr", "mean"),
        trades_per_session=("trades", "median"),
        mean_price=("mean_price", "median")).reset_index()
    stats = stats.merge(_rank_stability(control), on="symbol", how="left")
    stats["sessions_present"] = stats.symbol.map(presence).fillna(0).astype(int)

    total = len(stats)
    stats = stats[stats.symbol.isin(complete)]
    after_presence = len(stats)
    # The activity floor is a measurement criterion, not a size cut-off: below a couple of
    # hundred trades a session a one-second book snapshot sees nothing happen between
    # consecutive observations, so the microstructure measures are not identified.
    stats = stats[stats.trades_per_session >= args.min_trades]
    after_floor = len(stats)
    stats = stats[stats.rank_span.fillna(1.0) <= args.max_rank_span]
    after_stability = len(stats)
    stats = stats.sort_values("adv_inr", ascending=False).reset_index(drop=True)

    fo = load_fo_underlyings()
    fo_verified = fo is not None
    if fo_verified:
        derivative = stats[stats.symbol.isin(fo)].reset_index(drop=True)
        cash_only = stats[~stats.symbol.isin(fo)].reset_index(drop=True)
    else:
        logger.warning(
            f"[UNIVERSE] {FO_LIST.name} not found. The two derivative groups will be formed "
            f"on turnover alone and there will be no placebo group, so the report cannot "
            f"separate a settlement effect from a calendar effect. Download the NSE list of "
            f"securities available for trading in F&O and save one symbol per line to "
            f"{FO_LIST}.")
        derivative = stats
        cash_only = stats.iloc[0:0]

    size = args.group_size
    if len(derivative) < 2 * size:
        raise SystemExit(
            f"only {len(derivative)} securities survive the filters; two groups of {size} "
            f"need {2 * size}. Lower --group-size or --min-trades.")

    liquid = derivative.head(size)
    illiquid = derivative.tail(size)
    placebo_symbols = _match_placebo(cash_only, illiquid, size)

    members = {"liquid": liquid.symbol.tolist(),
               "illiquid": illiquid.symbol.tolist(),
               "placebo": placebo_symbols}
    balance = _balance(stats, members)

    # Where the placebo group's turnover range sits relative to each treated group. The
    # placebo can only be matched to the illiquid group - a security traded as heavily as the
    # liquid group and carrying no derivative barely exists, which is close to why the liquid
    # group has derivatives - so the report has to say which comparison it licenses.
    overlap = {}
    if placebo_symbols:
        placebo_adv = stats[stats.symbol.isin(placebo_symbols)].adv_inr
        for name, block in (("liquid", liquid), ("illiquid", illiquid)):
            low, high = placebo_adv.min(), placebo_adv.max()
            inside = block.adv_inr.between(low, high).mean()
            overlap[name] = round(float(inside), 3)

    payload = {
        "method": "turnover measured on control sessions only; placebo matched on turnover "
                  "and price",
        "sessions": len(sessions_seen),
        "control_sessions": len(control_sessions),
        "expiry_sessions": len(expiry_sessions),
        "group_size": size,
        "fo_verified": fo_verified,
        "filters": {
            "symbols_traded": total,
            "after_present_in_all_sessions": after_presence,
            "after_activity_floor": after_floor,
            "after_rank_stability": after_stability,
            "min_trades_per_session": args.min_trades,
            "max_rank_span": args.max_rank_span,
        },
        "placebo_adv_overlap": overlap,
        "groups": members,
        "balance": balance.to_dict("records"),
        "adv_cr": {row.symbol: round(row.adv_inr / 1e7, 3) for row in stats.itertuples()
                   if row.symbol in set().union(*[set(v) for v in members.values()])},
    }
    DERIVED_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    stats.to_csv(CONFIG_DIR / "universe_2022_candidates.csv", index=False)

    print(f"symbols traded                 : {total:,}")
    print(f"  present in all {len(sessions_seen)} sessions    : {after_presence:,}")
    print(f"  above {args.min_trades:.0f} trades/session    : {after_floor:,}")
    print(f"  rank stable                  : {after_stability:,}")
    print(f"derivatives list verified      : {fo_verified}")
    if overlap:
        print(f"placebo turnover covers        : "
              + ", ".join(f"{v:.0%} of {k}" for k, v in overlap.items()))
    print()
    print(balance.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"\nwrote {DERIVED_PATH}")
    if not placebo_symbols:
        print("\nNO PLACEBO GROUP. The report will state that expiry effects cannot be "
              "separated from calendar effects on this universe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
