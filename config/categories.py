"""The four raw feeds this pipeline ingests, and how each maps onto an nsetick layout.

This file replaces `schema_definitions.py`, which carried a hand-transcribed copy of the
NSE fixed-width byte offsets. Two copies of a byte layout is one copy too many: the git
history of this repository is five consecutive commits fixing a symbol offset that had
drifted from the specification, and every one of them produced output that looked valid.
nsetick embeds the layouts from `spec/layouts/*.toml` at compile time and version-selects
them by date and observed record length, so the offsets now live in exactly one place and
a mismatch is reported rather than silently mis-sliced.

What stays here is the part that is genuinely this project's: which feeds we want, what we
filter each one down to, and what to call the directory it lands in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from config.settings import CASH_SERIES_FILTER, FUTURES_INSTRUMENT_FILTER


@dataclass(frozen=True)
class Category:
    """One raw feed: where it comes from, how nsetick reads it, where it goes."""

    name: str            # directory name under data/parsed and data/enriched
    layout: str          # nsetick layout id
    file_prefix: str     # raw file name prefix, e.g. CASH_Orders
    where: str           # nsetick filter expression, validated against the layout
    required: bool       # a missing raw file for an optional feed is not an error
    multipart: bool      # FAO ships one session as _01.._nn streams


CATEGORIES: Dict[str, Category] = {
    "cash_orders": Category(
        name="cash_orders",
        layout="cm_orders",
        file_prefix="CASH_Orders",
        where=f"series == '{CASH_SERIES_FILTER}'",
        required=True,
        multipart=False,
    ),
    "cash_trades": Category(
        name="cash_trades",
        layout="cm_trades",
        file_prefix="CASH_Trades",
        where=f"series == '{CASH_SERIES_FILTER}'",
        required=True,
        multipart=False,
    ),
    # Stock futures only. The pipeline's basis and roll analysis compares a cash equity to
    # its own future, so index contracts and the whole option chain are dropped at parse
    # time rather than carried through four stages and filtered at the end.
    "fao_orders": Category(
        name="fao_orders",
        layout="fao_orders",
        file_prefix="FAO_Orders",
        where=f"instrument == '{FUTURES_INSTRUMENT_FILTER}'",
        required=False,
        multipart=True,
    ),
    "fao_trades": Category(
        name="fao_trades",
        layout="fao_trades",
        file_prefix="FAO_Trades",
        where=f"instrument == '{FUTURES_INSTRUMENT_FILTER}'",
        required=True,
        multipart=True,
    ),
}

CASH_CATEGORIES: Tuple[str, ...] = ("cash_orders", "cash_trades")
FAO_CATEGORIES: Tuple[str, ...] = ("fao_orders", "fao_trades")
