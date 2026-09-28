"""What the expiring future is priced on during the settlement window.

A stock future held to expiry in 2022 was settled by delivery. The long pays the final
settlement price for the shares and has received, through the final variation margin, the
difference between that price and the price at which the future was bought. The two cancel:
whatever the settlement price, the long ends up having paid the futures price for the shares.
An expiring future is therefore worth the shares, and in the last minutes of the window it
should track the current cash price, not the average that sets the settlement price. Had
stock futures been settled in cash against the average, they would track the average, which
by the last minutes is almost fully determined.

The test is the slope of the futures price on the cash price, both measured relative to the
settlement price, at minutes by which nearly all of the average is fixed. A slope near one
says the future is priced on the shares; a slope near zero that it is priced on the
settlement price. Using the settlement price as the reference introduces no common noise:
it is a constant for each security and session. Noise in the cash price biases the slope
toward zero, against the first reading.

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
        frame["fut_rel"] = 1e4 * np.log(frame.fut_vwap / frame.settle)
        frame["cash_rel"] = 1e4 * np.log(frame.cash_vwap / frame.settle)
        rows = []
        for flag, block in frame.groupby("is_expiry"):
            for subset, part in (("final five minutes", block[block.minute >= 25]),
                                 ("minute 28", block[block.minute == 28])):
                fit = fe_ols(part, "fut_rel", ["cash_rel"], fe=None, cluster="symbol")
                if fit is None:
                    continue
                rows.append({"is_expiry": flag, "subset": subset, "nobs": fit.nobs,
                             "clusters": fit.clusters,
                             "weight_fixed": float(part.weight_fixed.median()),
                             "gap_settle": float(part.fut_rel.abs().median()),
                             "gap_cash": float((part.fut_rel - part.cash_rel).abs().median()),
                             **fit.get("cash_rel")})
        pd.DataFrame(rows).to_csv(Path(RESULTS_DIR) / "s7_convergence_slope.csv", index=False)
    logger.info(f"[S7] {len(frame):,} symbol-minutes, {len(summary)} symbol-sessions")
    return summary


if __name__ == "__main__":
    print(run_s7_futures_convergence().groupby("is_expiry").mean(numeric_only=True).T)
