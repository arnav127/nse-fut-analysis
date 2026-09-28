"""How the expiring future is priced while its settlement price is being formed.

On an ordinary session a stock future trades at the cash price plus the cost of carry. On the
expiry session it settles at the average cash price of the last thirty minutes, so during
the window it is a claim on an average, part of which is already fixed. If the market prices
it that way, the future at minute m should sit at

    P_m = (VWAP so far * volume so far + S_m * volume still to come) / window volume

rather than at the current cash price S_m. The two differ by the gap between the average
already realised and the current price, weighted by how much of the window has passed.

Regressing the futures-cash basis on that gap separates the two descriptions. A slope near
one says the future is priced as the average it settles to; a slope near zero says it
follows the spot price, as it does on any other day. The control sessions give the second
benchmark.

The regression uses the realised window volume to weight the average, which the market does
not know in advance; it is a description of how the future is priced, not a trading rule.

Also recorded: how far the future's last trade ends from the settlement price, and how much
of the future's session volume trades in the window.
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
    ALL_TARGET_DATES,
    DERIVATIVE_SYMBOLS,
    ENRICHED_DATA_DIR,
    EXPIRY_THURSDAYS_DDMMYYYY,
    RESULTS_DIR,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
)
from config.universe import group_of  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.panel import fe_ols  # noqa: E402
from utils.paths import has_partitions, parsed_dir, session_to_date, session_to_iso  # noqa: E402

logger = setup_logger("Convergence", "stage6_insights.log")


def fao_sessions():
    return [s for s in ALL_TARGET_DATES
            if parsed_dir("fao_trades", s).is_dir()
            and any(parsed_dir("fao_trades", s).glob("symbol=*"))]


def _futures_minutes(conn, session: str, symbols) -> pd.DataFrame:
    pattern = (parsed_dir("fao_trades", session) / "symbol=*" / "*.parquet").as_posix()
    quoted = ", ".join(f"'{s}'" for s in symbols)
    day = session_to_iso(session)
    return conn.execute(f"""
        WITH f AS (
            SELECT symbol, expiry_date, txn_time, CAST(txn_time AS TIME) AS tt,
                   CAST(trade_price AS DOUBLE) / 100.0 AS px,
                   CAST(trade_quantity AS DOUBLE) AS q
            FROM read_parquet('{pattern}', hive_partitioning = true)
            WHERE instrument = 'FUTSTK' AND record_indicator = 'RM' AND trade_quantity > 0
              AND symbol IN ({quoted}) AND expiry_date >= DATE '{day}'
        ),
        near AS (SELECT symbol, MIN(expiry_date) AS near_expiry FROM f GROUP BY symbol),
        g AS (SELECT f.* FROM f JOIN near n ON f.symbol = n.symbol
                                          AND f.expiry_date = n.near_expiry)
        SELECT symbol,
               CAST(date_diff('minute', TIME '{SETTLEMENT_WINDOW_START}', tt) AS INTEGER)
                   AS minute,
               SUM(px * q) / SUM(q) AS fut_vwap,
               SUM(q) AS fut_volume,
               arg_max(px, txn_time) AS fut_last,
               any_value(expiry_date) AS expiry_date
        FROM g
        WHERE tt >= TIME '{SETTLEMENT_WINDOW_START}' AND tt <= TIME '{SETTLEMENT_WINDOW_END}'
        GROUP BY symbol, minute
        UNION ALL
        SELECT symbol, -1 AS minute, NULL, SUM(q), arg_max(px, txn_time),
               any_value(expiry_date)
        FROM g WHERE tt < TIME '{SETTLEMENT_WINDOW_START}'
        GROUP BY symbol
    """).df()


def _cash_minutes(conn, session: str, symbols) -> pd.DataFrame:
    pattern = (Path(ENRICHED_DATA_DIR) / "cash_trades" / f"date={session}" / "sym=*"
               / "*.parquet").as_posix()
    quoted = ", ".join(f"'{s}'" for s in symbols)
    return conn.execute(f"""
        SELECT symbol,
               CAST(date_diff('minute', TIME '{SETTLEMENT_WINDOW_START}',
                              CAST(txn_datetime AS TIME)) AS INTEGER) AS minute,
               SUM(trade_price * trade_quantity) / SUM(trade_quantity) AS cash_vwap,
               SUM(CAST(trade_quantity AS DOUBLE)) AS cash_volume
        FROM read_parquet('{pattern}')
        WHERE is_settlement_window AND is_regular_market AND trade_quantity > 0
          AND symbol IN ({quoted})
        GROUP BY symbol, minute
    """).df()


def run_s7_futures_convergence() -> pd.DataFrame:
    sessions = fao_sessions()
    out_csv = Path(RESULTS_DIR) / "s7_futures_convergence.csv"
    summary_csv = Path(RESULTS_DIR) / "s7_futures_summary.csv"
    if not sessions:
        logger.info("[S7] no parsed derivatives trades; skipped")
        return pd.DataFrame()
    symbols = list(DERIVATIVE_SYMBOLS)
    logger.info(f"[S7] {len(sessions)} sessions with derivatives trades")

    minutes, summaries = [], []
    with duckdb.connect() as conn:
        for session in sessions:
            fut = _futures_minutes(conn, session, symbols)
            cash = _cash_minutes(conn, session, symbols)
            if fut.empty or cash.empty:
                continue
            pre = fut[fut.minute == -1].set_index("symbol")
            fut = fut[fut.minute >= 0]
            # Trades stamped exactly 15:30:00 belong to the window's last minute.
            cash = cash[cash.minute >= 0].assign(minute=lambda c: c.minute.clip(upper=29))
            cash = (cash.assign(pv=cash.cash_vwap * cash.cash_volume)
                    .groupby(["symbol", "minute"], as_index=False)
                    .agg(pv=("pv", "sum"), cash_volume=("cash_volume", "sum")))
            cash["cash_vwap"] = cash.pv / cash.cash_volume
            fut["minute"] = fut.minute.clip(upper=29)
            fut = (fut.assign(pv=fut.fut_vwap * fut.fut_volume)
                   .groupby(["symbol", "minute"], as_index=False)
                   .agg(pv=("pv", "sum"), fut_volume=("fut_volume", "sum"),
                        fut_last=("fut_last", "last")))
            fut["fut_vwap"] = fut.pv / fut.fut_volume

            cash = cash.sort_values(["symbol", "minute"])
            cash["pv"] = cash.cash_vwap * cash.cash_volume
            cash["cum_pv"] = cash.groupby("symbol").pv.cumsum()
            cash["cum_v"] = cash.groupby("symbol").cash_volume.cumsum()
            total = cash.groupby("symbol").agg(total_v=("cash_volume", "sum"),
                                               total_pv=("pv", "sum"))
            total["settle"] = total.total_pv / total.total_v
            cash = cash.join(total, on="symbol")
            # The average as it will stand at the end if every remaining share trades at
            # the current price. At the last minute this is the settlement price itself.
            cash["projection"] = ((cash.cum_pv + cash.cash_vwap * (cash.total_v - cash.cum_v))
                                  / cash.total_v)
            cash["weight_fixed"] = cash.cum_v / cash.total_v

            merged = cash.merge(fut, on=["symbol", "minute"], how="inner")
            merged["session"] = session
            merged["is_expiry"] = session in EXPIRY_THURSDAYS_DDMMYYYY
            merged["basis_spot"] = 1e4 * np.log(merged.fut_vwap / merged.cash_vwap)
            merged["gap_projection"] = 1e4 * np.log(merged.projection / merged.cash_vwap)
            merged["basis_settle"] = 1e4 * np.log(merged.fut_vwap / merged.settle)
            minutes.append(merged)

            last = fut.sort_values("minute").groupby("symbol").tail(1).set_index("symbol")
            day_volume = fut.groupby("symbol").fut_volume.sum() + pre.fut_volume.reindex(
                fut.symbol.unique()).fillna(0)
            for symbol in last.index.intersection(total.index):
                pre_px = pre.fut_last.get(symbol, np.nan)
                summaries.append({
                    "symbol": symbol, "session": session,
                    "trade_date": session_to_iso(session),
                    "is_expiry": session in EXPIRY_THURSDAYS_DDMMYYYY,
                    "security_group": group_of(symbol),
                    "settle": total.settle[symbol],
                    "fut_last": last.fut_last[symbol],
                    "fut_close_gap_bps": abs(1e4 * np.log(last.fut_last[symbol]
                                                          / total.settle[symbol])),
                    "fut_window_share": float(fut[fut.symbol == symbol].fut_volume.sum()
                                              / day_volume.get(symbol, np.nan)),
                    "fut_pre_basis_bps": 1e4 * np.log(pre_px / total.settle[symbol])
                    if np.isfinite(pre_px) else np.nan,
                })

    frame = pd.concat(minutes, ignore_index=True) if minutes else pd.DataFrame()
    frame.to_csv(out_csv, index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(summary_csv, index=False)

    if not frame.empty:
        frame["pair"] = frame.symbol + "_" + frame.session
        rows = []
        for flag, block in frame.groupby("is_expiry"):
            fit = fe_ols(block, "basis_spot", ["gap_projection"], fe="pair", cluster="symbol")
            if fit is not None:
                rows.append({"is_expiry": flag, "nobs": fit.nobs, "clusters": fit.clusters,
                             **fit.get("gap_projection")})
            late = block[block.minute >= 20]
            fit = fe_ols(late, "basis_spot", ["gap_projection"], fe="pair", cluster="symbol")
            if fit is not None:
                rows.append({"is_expiry": flag, "subset": "final ten minutes",
                             "nobs": fit.nobs, "clusters": fit.clusters,
                             **fit.get("gap_projection")})
        pd.DataFrame(rows).to_csv(Path(RESULTS_DIR) / "s7_convergence_slope.csv", index=False)
    logger.info(f"[S7] {len(frame):,} symbol-minutes, {len(summary)} symbol-sessions")
    return summary


if __name__ == "__main__":
    print(run_s7_futures_convergence().groupby("is_expiry").mean(numeric_only=True).T)
