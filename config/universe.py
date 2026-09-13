"""The securities studied, and why they are grouped the way they are.

Three groups, not two.

`liquid` and `illiquid` are both derivatives-eligible. That is the point of the contrast:
both carry an expiring position whose settlement price is the cash VWAP, so both face the
same incentive, and the only thing that differs is what it costs to act on it. A contrast
between a mega-cap and a mid-cap that are *both* among the most traded securities on the
exchange is not a liquidity contrast at all - which is what the original ten-name universe
had, since every one of its "illiquid" names was a large-cap index constituent.

`placebo` is the group that makes the design work. These securities have no derivative
expiring on the Thursday, so the settlement mechanism gives nobody any reason to care about
their closing half-hour. If spreads widen and cancellations rise in the placebo group too,
the effect is a last-Thursday-of-the-month effect - month-end rebalancing, index events,
options on the index - and not a settlement effect. Without this group the study cannot
separate the two, and every result has to be hedged accordingly.

The lists here are a fallback. `scripts/build_universe.py` derives them from the tape
itself - average daily traded value computed from the 2022 sessions being studied, rather
than from a present-day index membership that did not exist in 2022 - and writes
`config/universe_2022.json`, which this module loads in preference. Group assignment from
today's index is the defect that would put a 2023 listing in a 2022 sample.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

CONFIG_DIR = Path(__file__).resolve().parent
DERIVED_PATH = CONFIG_DIR / "universe_2022.json"

# How many securities per group when the builder runs. Twenty is a compromise: enough that a
# per-group mean is not driven by one name, few enough that the enriched layer for a session
# stays within a few gigabytes. The paired tests gain power from sessions as much as from
# securities, and there are twelve matched months either way.
GROUP_SIZE = 20


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    derivatives_eligible: bool
    description: str
    symbols: List[str] = field(default_factory=list)


# Fallback membership, used when the builder has not been run.
#
# These are F&O underlyings that traded throughout 2022, sorted by rough turnover. They are
# a starting point for a first run, not the finished universe: `scripts/build_universe.py`
# replaces them with an ADV ranking measured from the sessions actually being studied, and
# records that it did so. Treat any result produced on the fallback as provisional.
_FALLBACK_LIQUID = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "SBIN", "AXISBANK", "KOTAKBANK", "ITC", "LT",
    "BHARTIARTL", "HINDUNILVR", "BAJFINANCE", "MARUTI", "ASIANPAINT",
    "TITAN", "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "WIPRO",
]
_FALLBACK_ILLIQUID = [
    "APOLLOHOSP", "DIVISLAB", "EICHERMOT", "BPCL", "CIPLA",
    "HEROMOTOCO", "BRITANNIA", "SHREECEM", "UPL", "COFORGE",
    "MFSL", "PVR", "IPCALAB", "ABFRL", "BALKRISIND",
    "ESCORTS", "GNFC", "LALPATHLAB", "NAVINFLUOR", "OFSS",
]
# Non-derivative securities of comparable size to the illiquid group. No expiring contract
# settles against their cash VWAP, so they should show no expiry effect.
_FALLBACK_PLACEBO = [
    "AARTIIND", "AAVAS", "AFFLE", "AJANTPHARM", "ALKYLAMINE",
    "APLLTD", "ASTRAL", "BLUEDART", "CAPLIPOINT", "CARBORUNIV",
    "CENTRALBK", "CERA", "CHAMBLFERT", "CREDITACC", "CYIENT",
    "FINEORG", "GRINDWELL", "JBCHEPHARM", "KEI", "SUPREMEIND",
]

GROUPS: Dict[str, Group] = {}


def _build(liquid: List[str], illiquid: List[str], placebo: List[str]) -> Dict[str, Group]:
    return {
        "liquid": Group(
            "liquid", "Liquid (derivatives-eligible)", True,
            "Most traded derivatives underlyings; marking the settlement is expensive here.",
            liquid),
        "illiquid": Group(
            "illiquid", "Illiquid (derivatives-eligible)", True,
            "Least traded derivatives underlyings; the same incentive at a far lower cost.",
            illiquid),
        "placebo": Group(
            "placebo", "Placebo (no derivatives)", False,
            "No contract settles against these. Any expiry-Thursday effect here is a "
            "calendar effect rather than a settlement effect.",
            placebo),
    }


def _load() -> Dict[str, Group]:
    """Prefer the derived universe; fall back to the checked-in lists."""
    if DERIVED_PATH.exists():
        try:
            payload = json.loads(DERIVED_PATH.read_text(encoding="utf-8"))
            groups = payload["groups"]
            return _build(groups["liquid"], groups["illiquid"], groups.get("placebo", []))
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    return _build(_FALLBACK_LIQUID, _FALLBACK_ILLIQUID, _FALLBACK_PLACEBO)


GROUPS = _load()

LIQUID_SYMBOLS: List[str] = list(GROUPS["liquid"].symbols)
ILLIQUID_SYMBOLS: List[str] = list(GROUPS["illiquid"].symbols)
PLACEBO_SYMBOLS: List[str] = list(GROUPS["placebo"].symbols)

# Everything the pipeline parses and enriches.
TARGET_SYMBOLS: List[str] = LIQUID_SYMBOLS + ILLIQUID_SYMBOLS + PLACEBO_SYMBOLS

# Securities that carry an expiring derivative. The hypotheses about settlement influence
# apply to these; the placebo group is the comparison that gives them meaning.
DERIVATIVE_SYMBOLS: List[str] = LIQUID_SYMBOLS + ILLIQUID_SYMBOLS

SYMBOL_GROUP: Dict[str, str] = {
    symbol: group.key for group in GROUPS.values() for symbol in group.symbols
}


def group_of(symbol: str) -> str:
    return SYMBOL_GROUP.get(symbol, "unknown")


def is_derived_universe() -> bool:
    """True when the membership came from the tape rather than from the fallback lists."""
    return DERIVED_PATH.exists()


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
