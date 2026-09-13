"""Is the window different because someone is pushing, or because more people are trading?

Almost every measure in the original design rises with activity. Spreads widen, cancellations
multiply, impact grows - and all of that happens whether the extra participants are trying to
move the settlement price or are hedging in the ordinary way. A study that only reports those
measures cannot tell the two apart, which is why its conclusions have to be hedged into
uselessness.

These three measures can tell them apart, because they respond to activity and to direction
with *opposite* signs.

**Variance ratio.** If prices are being pushed, successive returns lean the same way and the
variance of a sixty-second return exceeds sixty times the variance of a one-second return:
the ratio rises above one. If the window is simply busier and more two-sided, the extra
activity arrives as bid-ask bounce, successive returns offset, and the ratio falls below one.
More trading alone cannot push this statistic up.

**Order flow persistence.** The first-order autocorrelation of signed volume per second. One
participant working a large order in the same direction leaves a long positive tail; many
participants trading against each other do not.

**Impact decomposition.** Of the price move in the ten seconds after a trade, how much
survives sixty seconds later. A push that is genuinely moving the price leaves a permanent
component; liquidity demand that is absorbed reverts. Rising permanent share is evidence of
directional pressure, falling permanent share is evidence of congestion.

Read together these cut the other way from the activity measures, so agreement between them
is informative rather than mechanical.
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

from config.settings import CLOB_DATA_DIR, ENRICHED_DATA_DIR, RESULTS_DIR  # noqa: E402
from config.universe import group_of  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Pressure", "stage6_insights.log")

# The long horizon of the variance ratio, in seconds. Sixty is short enough that a
# thirty-minute window still contains thirty independent observations and long enough to span
# the horizon over which a working order would show.
VR_HORIZON_SECONDS = 60

# Trades are followed for this long to separate the part of their impact that persists from
# the part that reverts.
IMPACT_SHORT_SECONDS = 10
IMPACT_LONG_SECONDS = 60

MIN_SNAPSHOTS = 300


def _variance_ratio(mid: np.ndarray, horizon: int) -> float:
    """Lo-MacKinlay variance ratio of log mid returns at one-second and `horizon` sampling.

    A value of one means returns are serially uncorrelated. Above one is trending, below one
    is mean-reverting. The denominator scales by the horizon because variance accumulates
    linearly under a random walk, which is the null this is measured against.
    """
    price = mid[np.isfinite(mid) & (mid > 0)]
    if price.size < horizon * 5:
        return np.nan
    log_price = np.log(price)
    short = np.diff(log_price)
    long = log_price[horizon:] - log_price[:-horizon]
    var_short = short.var(ddof=1)
    if var_short <= 0 or long.size < 5:
        return np.nan
    return float(long.var(ddof=1) / (horizon * var_short))


def _autocorrelation(series: np.ndarray, lag: int = 1) -> float:
    values = series[np.isfinite(series)]
    if values.size <= lag + 5 or values.std() == 0:
        return np.nan
    a, b = values[:-lag], values[lag:]
    if a.std() == 0 or b.std() == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def _signed_flow_per_second(trades: pd.DataFrame) -> pd.Series:
    """Net signed volume for each second of the window, by the tick rule."""
    price = trades.trade_price.to_numpy(dtype=float)
    qty = trades.qty.to_numpy(dtype=float)
    sign = np.sign(np.diff(price, prepend=price[0]))
    # Zero ticks inherit the previous direction: a run of same-price trades is one side
    # working through resting depth, not a sequence of unsigned trades.
    for i in range(1, sign.size):
        if sign[i] == 0:
            sign[i] = sign[i - 1]
    seconds = trades.txn_datetime.dt.floor("s")
    return pd.Series(sign * qty, index=seconds.to_numpy()).groupby(level=0).sum()


def _flow_and_impact(trades: pd.DataFrame, book: pd.DataFrame) -> dict:
    """Signed-flow persistence, and how much of a move survives a minute later.

    Impact is measured on the *mid*, not on trade prices, and from the second in which the
    flow arrived rather than from the trade itself.

    Measuring it on trade prices does not work here, and the failure is not small. The tick
    rule assigns a buy after an uptick, and part of every uptick is the bid-ask bounce; the
    subsequent return then contains that bounce reverting, so the measured "impact" of a buy
    comes out negative and the permanent share becomes a ratio of two negative numbers that
    means nothing. The mid has no bounce, so the same calculation on mids isolates the price
    change that the flow actually caused.
    """
    if len(trades) < 50 or len(book) < MIN_SNAPSHOTS:
        return {}

    trades = trades.sort_values("txn_datetime")
    flow = _signed_flow_per_second(trades)
    result = {
        "flow_autocorr": _autocorrelation(flow.to_numpy(), lag=1),
        "sign_autocorr": _autocorrelation(np.sign(flow.to_numpy()), lag=1),
    }

    # Align the flow onto the one-second book grid.
    grid = book.set_index(book.snapshot_time.dt.floor("s"))
    mid = grid.midpoint.astype(float)
    mid = mid[~mid.index.duplicated(keep="first")]
    aligned = flow.reindex(mid.index).fillna(0.0)

    values = mid.to_numpy()
    net = aligned.to_numpy()
    n = values.size
    if n < IMPACT_LONG_SECONDS * 3:
        return result

    # Only seconds carrying meaningful one-sided flow. Every second contains some trading,
    # and averaging over all of them measures nothing but noise around zero.
    magnitude = np.abs(net)
    active = magnitude > 0
    if active.sum() < 30:
        return result
    threshold = np.median(magnitude[active])
    events = np.flatnonzero(active & (magnitude >= threshold))
    events = events[events + IMPACT_LONG_SECONDS < n]
    if events.size < 30:
        return result

    direction = np.sign(net[events])
    base = values[events]
    short = direction * (values[events + IMPACT_SHORT_SECONDS] - base) / base * 10000.0
    long = direction * (values[events + IMPACT_LONG_SECONDS] - base) / base * 10000.0

    mean_short = float(short.mean())
    mean_long = float(long.mean())
    result.update({
        "n_impact_events": int(events.size),
        "impact_short_bps": mean_short,
        "impact_long_bps": mean_long,
        # Only meaningful when the flow moved the price in its own direction to begin with.
        # A ratio taken against a near-zero or negative denominator is not a share of
        # anything, and reporting one would put a number where there is no measurement.
        "permanent_share": mean_long / mean_short if mean_short > 0.05 else np.nan,
    })
    return result


def run_s2_pressure_or_activity() -> pd.DataFrame:
    snaps = (Path(CLOB_DATA_DIR) / "date=*" / "sym=*" / "*.parquet").as_posix()
    tape = (Path(ENRICHED_DATA_DIR) / "cash_trades" / "date=*" / "sym=*" / "*.parquet").as_posix()
    out_csv = Path(RESULTS_DIR) / "s2_pressure_or_activity.csv"

    logger.info("[S2] variance ratios, flow persistence and impact decomposition")

    with duckdb.connect() as conn:
        books = conn.execute(f"""
            SELECT symbol, session, trade_date, is_expiry, snapshot_time, midpoint
            FROM read_parquet('{snaps}')
            WHERE midpoint IS NOT NULL AND midpoint > 0
            ORDER BY symbol, trade_date, snapshot_time
        """).df()
        tapes = conn.execute(f"""
            SELECT symbol, trade_date, txn_datetime, trade_price,
                   CAST(trade_quantity AS DOUBLE) AS qty
            FROM read_parquet('{tape}')
            WHERE is_settlement_window AND is_regular_market AND trade_quantity > 0
            ORDER BY symbol, trade_date, txn_datetime
        """).df()

    tape_groups = dict(tuple(tapes.groupby(["symbol", "trade_date"])))

    rows = []
    for (symbol, trade_date), book in books.groupby(["symbol", "trade_date"]):
        if len(book) < MIN_SNAPSHOTS:
            continue
        mid = book.midpoint.to_numpy(dtype=float)
        record = {
            "symbol": symbol,
            "trade_date": trade_date,
            "session": book.session.iloc[0],
            "is_expiry": bool(book.is_expiry.iloc[0]),
            "security_group": group_of(symbol),
            "n_snapshots": len(book),
            "variance_ratio": _variance_ratio(mid, VR_HORIZON_SECONDS),
            "mid_return_autocorr": _autocorrelation(np.diff(np.log(mid))),
        }
        record.update(_flow_and_impact(
            tape_groups.get((symbol, trade_date), pd.DataFrame()), book))
        rows.append(record)

    result = pd.DataFrame(rows)
    result.to_csv(out_csv, index=False)
    logger.info(f"[S2] {len(result)} symbol-sessions -> {out_csv}")
    return result


if __name__ == "__main__":
    frame = run_s2_pressure_or_activity()
    print(frame.groupby("is_expiry")[
        ["variance_ratio", "mid_return_autocorr", "flow_autocorr", "sign_autocorr",
         "impact_short_bps", "impact_long_bps", "permanent_share"]].mean().to_string())
