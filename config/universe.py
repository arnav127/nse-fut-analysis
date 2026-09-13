"""The securities studied, and why they are grouped the way they are.

Three groups.

`liquid` and `illiquid` are both derivatives underlyings. That is the point of the contrast:
both carry an expiring position whose settlement price is the cash VWAP, so both face the
same incentive, and what differs is the cost of acting on it. A contrast between two
securities that are both among the most traded on the exchange is not a liquidity contrast,
whatever their relative size - which is what the original five-and-five universe had, since
every one of its "illiquid" names was a large-cap index constituent.

`placebo` is the group that makes the design work. These securities have no derivative
expiring on the Thursday, so the settlement mechanism gives nobody any reason to care about
their closing half hour. If spreads widen and cancellations rise there too, the effect
belongs to the last Thursday of the month - month-end flows, index rebalancing, index option
expiry - and not to the settlement. Without this group the two cannot be separated and every
result has to be reported with that caveat attached.

Membership comes from `scripts/build_universe.py`, which ranks securities on turnover
measured from the control sessions only - grouping on expiry-day activity would make the
group variable a function of the outcome - and matches the placebo group to the illiquid
group on both turnover and price level. It writes `config/universe_2022.json`, which this
module loads in preference to the development list below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

CONFIG_DIR = Path(__file__).resolve().parent
DERIVED_PATH = CONFIG_DIR / "universe_2022.json"

# Securities per group when the builder runs.
#
# Fifty. The difference-in-differences in the report are two-sample comparisons over
# securities, not over security-months: the twelve months of one security are not twelve
# independent observations of how that security responds. At fifty per group those tests
# detect an effect of about 0.57 standard deviations at conventional power, which is the
# range the paired results sit in. At twenty they detect almost nothing, which is what the
# first run of those contrasts showed.
GROUP_SIZE = 50


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    derivatives_eligible: bool
    description: str
    symbols: List[str] = field(default_factory=list)


# Development universe, used when the builder has not been run.
#
# Deliberately the original ten names and no placebo group. Inventing fifty plausible-looking
# tickers per group would produce a universe that runs, looks like the study universe in
# every log line, and is not one - and a placebo list assembled by hand would be asserting
# derivatives eligibility that nothing checked. Anything produced on this universe is a smoke
# test. `is_derived_universe()` is false here, and the report says so.
_DEV_LIQUID = ["RELIANCE", "TCS", "ICICIBANK", "HDFCBANK", "INFY"]
_DEV_ILLIQUID = ["DIVISLAB", "CIPLA", "EICHERMOT", "BPCL", "APOLLOHOSP"]


def _build(liquid: List[str], illiquid: List[str], placebo: List[str]) -> Dict[str, Group]:
    return {
        "liquid": Group(
            "liquid", "Liquid (derivatives)", True,
            "Most traded derivatives underlyings; moving the settlement is expensive here.",
            liquid),
        "illiquid": Group(
            "illiquid", "Illiquid (derivatives)", True,
            "Least traded derivatives underlyings; the same incentive, far cheaper to act on.",
            illiquid),
        "placebo": Group(
            "placebo", "Placebo (no derivatives)", False,
            "No contract settles against these, so an expiry-Thursday effect here is a "
            "calendar effect rather than a settlement effect.",
            placebo),
    }


def _load() -> Dict[str, Group]:
    if DERIVED_PATH.exists():
        try:
            payload = json.loads(DERIVED_PATH.read_text(encoding="utf-8"))
            groups = payload["groups"]
            return _build(groups.get("liquid", []), groups.get("illiquid", []),
                          groups.get("placebo", []))
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    return _build(_DEV_LIQUID, _DEV_ILLIQUID, [])


def _meta() -> dict:
    if not DERIVED_PATH.exists():
        return {}
    try:
        return json.loads(DERIVED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


GROUPS = _load()
META = _meta()

LIQUID_SYMBOLS: List[str] = list(GROUPS["liquid"].symbols)
ILLIQUID_SYMBOLS: List[str] = list(GROUPS["illiquid"].symbols)
PLACEBO_SYMBOLS: List[str] = list(GROUPS["placebo"].symbols)

# Everything the pipeline parses and enriches.
TARGET_SYMBOLS: List[str] = LIQUID_SYMBOLS + ILLIQUID_SYMBOLS + PLACEBO_SYMBOLS

# Securities carrying an expiring derivative. The settlement hypotheses apply to these; the
# placebo group is the comparison that gives them meaning.
DERIVATIVE_SYMBOLS: List[str] = LIQUID_SYMBOLS + ILLIQUID_SYMBOLS

SYMBOL_GROUP: Dict[str, str] = {
    symbol: group.key for group in GROUPS.values() for symbol in group.symbols
}


def group_of(symbol: str) -> str:
    return SYMBOL_GROUP.get(symbol, "unknown")


def is_derived_universe() -> bool:
    """True when membership came from the tape rather than from the development list."""
    return DERIVED_PATH.exists() and bool(META.get("groups", {}).get("liquid"))


def has_placebo() -> bool:
    return bool(PLACEBO_SYMBOLS)


def sql_case(alias: str = "security_group", column: str = "symbol") -> str:
    """A DuckDB CASE mapping symbol to group key, for use inside the analysis queries.

    `column` is qualified by the caller because these queries join several relations that
    each carry a `symbol`, and an unqualified reference binds to none of them.
    """
    arms = []
    for group in GROUPS.values():
        if not group.symbols:
            continue
        members = ", ".join(f"'{s}'" for s in group.symbols)
        arms.append(f"WHEN {column} IN ({members}) THEN '{group.key}'")
    if not arms:
        return f"'unknown' AS {alias}"
    return "CASE " + " ".join(arms) + f" ELSE 'unknown' END AS {alias}"
