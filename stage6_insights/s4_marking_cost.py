"""What it would cost to move the settlement price.

This is the question the study is really about, and it is answerable directly from the
reconstructed book rather than by inference from spreads and depth.

For each snapshot, sweep the displayed book outward from the touch by a fixed notional and
record how far the price moves. Each side is swept separately, because the two are not
symmetric and the asymmetry is informative: a participant who wants the settlement higher has
to lift offers, so the depth of the ask side is what constrains them.

The result is an estimate of what marking the settlement would take, and it is a lower bound
rather than a price: the sweep assumes the book does not replenish and that nobody reacts,
and both assumptions flatter the attacker. Read it as an order of magnitude and as a
comparison between groups and sessions, not as a number of rupees.

The measure is what makes the liquid/illiquid contrast concrete. If the cost is an order of
magnitude lower in the illiquid group, then the same incentive faces a far weaker constraint
there, and that is a statement about where to look for an effect rather than an assumption
about it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402

from config.settings import CLOB_DATA_DIR, CLOB_REPORTED_LEVELS, RESULTS_DIR  # noqa: E402
from config.universe import group_of  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("MarkCost", "stage6_insights.log")

# The question is asked the other way round: not "what does a ten basis point move cost"
# but "how far does a given order move the price".
#
# The first form is censored. The snapshot carries a fixed number of levels, and on a liquid
# security ten basis points lies beyond all of them - in the first run of this measure the
# target was unreachable in ninety-three to a hundred per cent of snapshots, so every
# reported cost was a lower bound of unknown tightness and the liquid/illiquid comparison
# was between two censored numbers. Consuming a fixed notional and measuring the resulting
# move is never censored as long as the book holds that much, and the share of snapshots
# where it does not is reported.
#
# Two sizes, both small enough that the displayed book usually holds them. Half a crore
# already exhausts the visible book of a thinly traded name in over ninety per cent of
# snapshots, which is itself the finding - the displayed book on those securities is smaller
# than a single institutional clip - but a probe that is censored everywhere measures
# nothing, so the reported sizes are ones the book can absorb and `thin_share` records how
# often even those could not be filled.
PROBE_NOTIONAL_CR = (0.1, 0.5)

# Snapshots are sampled rather than all used. The walk is a per-row loop over levels and the
# book barely changes second to second, so every tenth snapshot gives the same window average
# at a tenth of the cost.
SAMPLE_EVERY = 10


def _sweep(prices: np.ndarray, sizes: np.ndarray, mid: np.ndarray,
           budget_rupees: float) -> tuple:
    """Move, in bps, from consuming `budget_rupees` of displayed size. Vectorised over rows.

    Returns (move_bps, exhausted) where `exhausted` marks rows whose displayed book held
    less than the budget - there the move is a lower bound and the row is excluded from the
    averages rather than reported as though the walk completed.
    """
    notional = prices * sizes
    cumulative = np.nancumsum(np.where(np.isfinite(notional), notional, 0.0), axis=1)
    total = cumulative[:, -1]

    # The level at which the budget runs out. searchsorted per row, without a Python loop.
    reached = cumulative >= budget_rupees
    level = np.where(reached.any(axis=1), reached.argmax(axis=1), prices.shape[1] - 1)
    final_price = prices[np.arange(prices.shape[0]), level]

    move = np.abs(final_price - mid) / mid * 10000.0
    exhausted = total < budget_rupees
    return np.where(exhausted, np.nan, move), exhausted


def run_s4_marking_cost() -> pd.DataFrame:
    snaps = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    out_csv = Path(RESULTS_DIR) / "s4_marking_cost.csv"
    levels = CLOB_REPORTED_LEVELS

    price_cols = [f"{side}_px_{i}" for side in ("bid", "ask") for i in range(1, levels + 1)]
    size_cols = [f"{side}_depth_{i}" for side in ("bid", "ask") for i in range(1, levels + 1)]

    logger.info(f"[S4] sweeping the book for {PROBE_NOTIONAL_CR} crore probes")

    with duckdb.connect() as conn:
        available = {row[0] for row in
                     conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{snaps}')").fetchall()}
        if not set(price_cols) <= available:
            logger.error("[S4] snapshots carry no level prices; re-run the CLOB stage so the "
                         "flattened snapshots include bid_px_* and ask_px_*")
            return pd.DataFrame()

        frame = conn.execute(f"""
            SELECT symbol, session, trade_date, is_expiry, seconds_from_1500, midpoint,
                   {', '.join(price_cols + size_cols)}
            FROM read_parquet('{snaps}')
            WHERE midpoint IS NOT NULL AND midpoint > 0
              AND seconds_from_1500 % {SAMPLE_EVERY} = 0
            ORDER BY symbol, trade_date, seconds_from_1500
        """).df()

    if frame.empty:
        logger.warning("[S4] no snapshots")
        return pd.DataFrame()

    mid = frame.midpoint.to_numpy(dtype=float)
    ask_px = frame[[f"ask_px_{i}" for i in range(1, levels + 1)]].to_numpy(dtype=float)
    ask_qty = frame[[f"ask_depth_{i}" for i in range(1, levels + 1)]].to_numpy(dtype=float)
    bid_px = frame[[f"bid_px_{i}" for i in range(1, levels + 1)]].to_numpy(dtype=float)
    bid_qty = frame[[f"bid_depth_{i}" for i in range(1, levels + 1)]].to_numpy(dtype=float)

    aggregations = {
        "visible_notional_cr": ("visible_notional_cr", "median"),
        "snapshots": ("midpoint", "size"),
    }
    for budget_cr in PROBE_NOTIONAL_CR:
        tag = f"{budget_cr:g}".replace(".", "p")
        budget = budget_cr * 1e7
        up, up_out = _sweep(ask_px, ask_qty, mid, budget)
        down, down_out = _sweep(bid_px, bid_qty, mid, budget)
        frame[f"move_up_{tag}"] = up
        frame[f"move_down_{tag}"] = down
        # Both sides missing means the book could not absorb the probe either way; nanmean
        # over two NaNs warns and returns NaN, which is the right value without the warning.
        with np.errstate(invalid="ignore"):
            both = np.vstack([up, down])
            frame[f"move_{tag}"] = np.where(np.isnan(both).all(axis=0), np.nan,
                                            np.nanmean(np.where(np.isnan(both), np.nan, both),
                                                       axis=0))
        frame[f"thin_{tag}"] = up_out | down_out
        aggregations[f"move_up_bps_{tag}"] = (f"move_up_{tag}", "median")
        aggregations[f"move_down_bps_{tag}"] = (f"move_down_{tag}", "median")
        aggregations[f"move_bps_{tag}"] = (f"move_{tag}", "median")
        aggregations[f"thin_share_{tag}"] = (f"thin_{tag}", "mean")

    # Displayed notional across the reported levels: the book's total visible capacity, and
    # the denominator behind any statement about how much size the market can absorb.
    visible = np.nansum(ask_px * ask_qty, axis=1) + np.nansum(bid_px * bid_qty, axis=1)
    frame["visible_notional_cr"] = visible / 1e7

    grouped = frame.groupby(["symbol", "session", "trade_date", "is_expiry"],
                            as_index=False).agg(**aggregations)
    grouped["security_group"] = grouped.symbol.map(group_of)
    # Positive means it costs more to push the price up than down, which is what a book
    # leaning to the bid looks like from the perspective of somebody trying to mark higher.
    small = f"{PROBE_NOTIONAL_CR[0]:g}".replace(".", "p")
    grouped["move_asymmetry"] = (
        (grouped[f"move_up_bps_{small}"] - grouped[f"move_down_bps_{small}"])
        / grouped[[f"move_up_bps_{small}", f"move_down_bps_{small}"]].mean(axis=1))

    grouped.to_csv(out_csv, index=False)
    logger.info(f"[S4] {len(grouped)} symbol-sessions -> {out_csv}")
    return grouped


if __name__ == "__main__":
    result = run_s4_marking_cost()
    if not result.empty:
        cols = [c for c in result.columns
                if c.startswith(("move_bps", "move_up_bps", "thin_share", "visible_notional"))]
        print(result.groupby(["security_group", "is_expiry"])[cols].median().to_string())
