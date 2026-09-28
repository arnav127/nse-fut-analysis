"""Does the settlement price gravitate to option strikes on expiry?

Stock options on the exchange are exercised against the same settlement price as the
futures, so a holder of a large option position has an interest in where that price falls
relative to a strike. Two mechanisms push the closing price toward strikes on expiry
(Ni, Pearson and Poteshman 2005): the delta hedges of option writers, which lean against
moves away from a heavily held strike, and deliberate trading by option holders. Either way
the signature is the same. On the expiry session the settlement price ends closer to a
strike than it does on other sessions, and closer than the price stood before the window.

    distance   |settlement price - nearest strike| / strike interval, in [0, 0.5]

Under no attraction the distance is uniform, with mean one quarter. Two comparisons:

  across sessions   the expiry session against every other session of the same expiry
                    month, security by security, on the same strike grid
  within session    the distance at the settlement price against the distance at the
                    pre-window price, on the expiry session and on the others

The strike grid is read from the option trades themselves: every stock option strike traded
for the security on the expiry session or the session before it.
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

from config.settings import (  # noqa: E402
    DERIVATIVE_SYMBOLS,
    EXPIRY_CONTROL_PAIRS,
    RESULTS_DIR,
)
from utils.logger import setup_logger  # noqa: E402
from utils.panel import fe_ols  # noqa: E402
from utils.paths import parsed_dir, session_to_date  # noqa: E402

logger = setup_logger("Pinning", "stage6_insights.log")

# Strikes further than this from the price do not define the local interval.
LOCAL_BAND = 0.15


def _strikes(conn, sessions, symbols) -> pd.DataFrame:
    parts = []
    for s in sessions:
        d = parsed_dir("fao_trades", s)
        if d.is_dir() and any(d.glob("symbol=*")):
            parts.append((d / "symbol=*" / "*.parquet").as_posix())
    if not parts:
        return pd.DataFrame()
    files = ", ".join(f"'{p}'" for p in parts)
    quoted = ", ".join(f"'{s}'" for s in symbols)
    return conn.execute(f"""
        SELECT symbol, CAST(strike_price AS DOUBLE) / 100.0 AS strike,
               SUM(CAST(trade_quantity AS DOUBLE)) AS option_volume
        FROM read_parquet([{files}], hive_partitioning = true)
        WHERE instrument = 'OPTSTK' AND symbol IN ({quoted}) AND strike_price > 0
        GROUP BY symbol, strike
    """).df()


def _distance(price: np.ndarray, grid: np.ndarray) -> tuple:
    """Distance to the nearest strike in units of the local strike interval."""
    if grid.size < 3 or not np.isfinite(price):
        return np.nan, np.nan
    band = grid[np.abs(grid / price - 1.0) <= LOCAL_BAND]
    if band.size < 3 or price < grid.min() or price > grid.max():
        return np.nan, np.nan
    interval = float(np.median(np.diff(np.sort(band))))
    if interval <= 0:
        return np.nan, np.nan
    nearest = grid[np.argmin(np.abs(grid - price))]
    return float(abs(price - nearest) / interval), float(nearest)


def run_s8_strike_pinning() -> pd.DataFrame:
    panel_path = Path(RESULTS_DIR) / "s9_panel.parquet"
    out_csv = Path(RESULTS_DIR) / "s8_strike_pinning.csv"
    if not panel_path.exists():
        logger.info("[S8] no daily panel; run the tape stage first")
        return pd.DataFrame()
    panel = pd.read_parquet(panel_path)
    panel = panel[panel.symbol.isin(DERIVATIVE_SYMBOLS)]

    rows = []
    with duckdb.connect() as conn:
        for expiry, control in EXPIRY_CONTROL_PAIRS:
            grid = _strikes(conn, [expiry, control], list(DERIVATIVE_SYMBOLS))
            if grid.empty:
                continue
            end = session_to_date(expiry)
            # Sessions of the expiry month: after the previous monthly expiry, up to this one.
            earlier = [session_to_date(e) for e, _ in EXPIRY_CONTROL_PAIRS
                       if session_to_date(e) < end]
            start = max(earlier) if earlier else None
            month = panel[(panel.date <= end) & ((panel.date > start) if start else True)]
            grids = {s: g.strike.to_numpy() for s, g in grid.groupby("symbol")}
            volume = grid.groupby("symbol").option_volume.sum()
            for row in month.itertuples():
                strikes = grids.get(row.symbol)
                if strikes is None:
                    continue
                d_settle, k_settle = _distance(row.settle_vwap, strikes)
                reference = row.pre10_vwap if np.isfinite(row.pre10_vwap) else row.pre_last
                d_pre, _ = _distance(reference, strikes)
                rows.append({
                    "symbol": row.symbol, "session": row.session, "expiry_session": expiry,
                    "is_expiry": row.session == expiry, "day_type": row.day_type,
                    "group": row.group, "distance": d_settle, "distance_pre": d_pre,
                    "nearest_strike": k_settle,
                    "option_volume": float(volume.get(row.symbol, np.nan)),
                    "turnover": row.turnover,
                })
    frame = pd.DataFrame(rows).dropna(subset=["distance"])
    frame.to_csv(out_csv, index=False)
    if frame.empty:
        return frame

    # Option activity relative to the security's own cash turnover, split at the median:
    # attraction to strikes should be stronger where option positions are larger.
    activity = (frame.groupby("symbol").option_volume.first()
                / frame.groupby("symbol").turnover.median())
    frame["high_option"] = frame.symbol.map(activity > activity.median()).astype(float)
    frame["expiry"] = frame.is_expiry.astype(float)
    frame["expiry_x_high"] = frame.expiry * frame.high_option
    frame["change"] = frame.distance - frame.distance_pre
    frame["near"] = (frame.distance <= 0.1).astype(float)
    # Security by expiry month: the comparison is within a security and a strike grid.
    frame["symbol_month"] = frame.symbol + "_" + frame["expiry_session"]

    results = []
    for y in ("distance", "near", "change"):
        fit = fe_ols(frame, y, ["expiry"], fe="symbol_month", cluster="session")
        if fit is not None:
            base = frame.loc[frame.expiry == 0, y].mean()
            results.append({"outcome": y, "term": "expiry", "control_mean": base,
                            "nobs": fit.nobs, "sessions": fit.clusters, **fit.get("expiry")})
        fit = fe_ols(frame, y, ["expiry", "expiry_x_high"], fe="symbol_month",
                     cluster="session")
        if fit is not None:
            results.append({"outcome": y, "term": "expiry_x_high", "nobs": fit.nobs,
                             "sessions": fit.clusters, **fit.get("expiry_x_high")})
    pd.DataFrame(results).to_csv(Path(RESULTS_DIR) / "s8_pinning_tests.csv", index=False)
    logger.info(f"[S8] {len(frame):,} security-sessions on {frame.expiry.sum():.0f} "
                f"expiry observations")
    return frame


if __name__ == "__main__":
    print(pd.read_csv(Path(RESULTS_DIR) / "s8_pinning_tests.csv")
          if run_s8_strike_pinning() is not None else "")
