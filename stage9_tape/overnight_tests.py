"""Is the next morning's reversal after a monthly expiry news, or the release of the window?

On monthly expiries part of the settlement window's move is undone by the next morning. News
or information that arrives after the close would also move the next morning's price, so the
reversal is tested against that explanation in five ways:

  by expiry     the reversal estimated separately for each of the twelve expiries, to see
                whether it is spread across the year or carried by a few news-heavy dates;
  news days     stock-days with a sign of news the next morning, abnormal volume or an
                unusually large opening gap, removed;
  market news   the next morning's return adjusted for each security's exposure to the
                market, so that overnight market news that moves high-beta stocks more does
                not appear as a reversal;
  earlier move  the same regression on the move from the morning to the window: news that
                arrives overnight is unrelated to which part of the day a move took place in,
                while a release of the window reverses only the window's move;
  timing        the return split into the opening gap, the first half hour and the rest of
                the next day, to see where the reversal occurs and whether it lasts.

Reads the security-session panel (s9_panel.parquet) and the per-session tape for the next
day's open, close and volume.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402
from utils.panel import fe_ols, winsorize  # noqa: E402

EVENT_TYPES = ["monthly_expiry", "weekly_expiry", "month_end"]
TWO_WAY = ("symbol", "session")
GROUP_SETS = {"derivative": ["liquid", "illiquid"], "liquid": ["liquid"],
              "illiquid": ["illiquid"], "placebo": ["placebo"]}
NEWS_VOLUME = 2.0     # next-day volume above this multiple of the security's median
NEWS_GAP_Q = 0.95     # opening gap above this quantile of the security's own gaps


def load() -> pd.DataFrame:
    out = Path(RESULTS_DIR)
    panel = pd.read_parquet(out / "s9_panel.parquet")
    tape = pd.concat([pd.read_parquet(f, columns=["session", "symbol", "open_price",
                                                  "open30_vwap", "settle_vwap", "volume"])
                      for f in sorted((out / "tape").glob("session=*.parquet"))])
    nxt = tape.rename(columns={"session": "next_session", "open_price": "next_open",
                               "open30_vwap": "next_open30", "settle_vwap": "next_settle",
                               "volume": "next_volume"})
    panel = panel.merge(nxt, on=["symbol", "next_session"], how="left")
    bps = 1e4
    panel["gap"] = bps * np.log(panel.next_open / panel.settle_vwap)
    panel["morning"] = bps * np.log(panel.next_open30 / panel.next_open)
    panel["rest_of_day"] = bps * np.log(panel.next_settle / panel.next_open30)
    panel["next_day"] = bps * np.log(panel.next_settle / panel.settle_vwap)
    reference = panel.pre10_vwap.fillna(panel.pre_last)
    panel["day_move"] = bps * np.log(reference / panel.open30_vwap)
    for c in ("gap", "morning", "rest_of_day", "next_day", "day_move"):
        panel[c] = panel.groupby("group")[c].transform(winsorize)

    # Signs of news the next morning.
    median_volume = panel.groupby("symbol").volume.transform("median")
    panel["abnormal_volume"] = panel.next_volume / median_volume
    gap_cut = panel.groupby("symbol").gap.transform(lambda g: g.abs().quantile(NEWS_GAP_Q))
    panel["news"] = (panel.abnormal_volume > NEWS_VOLUME) | (panel.gap.abs() > gap_cut)

    # Exposure to the market: beta of the close-to-close return on the equal-weighted
    # universe, estimated over the year; the market's next-morning return is the universe
    # average on that session.
    panel = panel.sort_values(["symbol", "date"])
    panel["cc"] = bps * np.log(panel.settle_vwap / panel.groupby("symbol").settle_vwap.shift())
    market_cc = panel.groupby("session").cc.transform("mean")
    cov = (panel.cc * market_cc).groupby(panel.symbol).mean() - (
        panel.cc.groupby(panel.symbol).mean() * market_cc.groupby(panel.symbol).mean())
    beta = cov / market_cc.groupby(panel.symbol).var(ddof=0)
    panel["beta"] = panel.symbol.map(beta)
    market_next = panel.groupby("session").next_rev.transform("mean")
    panel["next_rev_beta"] = panel.next_rev - panel.beta * market_next
    for t in EVENT_TYPES:
        panel[f"day_move_x_{t}"] = panel.day_move * panel[t]
    return panel


def _x(move: str = "drift") -> List[str]:
    return [move, *[f"{move}_x_{t}" for t in EVENT_TYPES], *EVENT_TYPES]


def reversal(frame: pd.DataFrame, y: str = "next_rev", move: str = "drift",
             extra: List[str] = ()) -> Dict[str, float]:
    fit = fe_ols(frame, y, _x(move) + list(extra), fe=TWO_WAY)
    if fit is None:
        return {}
    base, add = fit.get(move), fit.get(f"{move}_x_monthly_expiry")
    return {"base": base["coef"], "base_se": base["se"], "expiry": add["coef"],
            "expiry_se": add["se"], "expiry_p": add["p"], "nobs": fit.nobs}


def robustness_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, groups in GROUP_SETS.items():
        frame = panel[panel.group.isin(groups)]
        quiet = frame[~frame.news.fillna(False)]
        both = frame.assign(day_move=frame.day_move)
        specs = {
            "baseline": reversal(frame),
            "without news days": reversal(quiet),
            "beta-adjusted": reversal(frame, y="next_rev_beta"),
            "without 24 Feb 2022": reversal(frame[frame.session != "24022022"]),
            "beta-adjusted, without news days": reversal(quiet, y="next_rev_beta"),
            "earlier move (open to window)": reversal(frame, move="day_move"),
            "window move, controlling earlier move": reversal(
                both, extra=["day_move", *[f"day_move_x_{t}" for t in EVENT_TYPES]]),
        }
        for horizon in ("gap", "morning", "rest_of_day", "next_day"):
            specs[f"horizon: {horizon}"] = reversal(frame, y=horizon)
        for name, r in specs.items():
            rows.append({"sample": key, "spec": name, **r})
    out = pd.DataFrame(rows)
    news_share = panel.groupby("monthly_expiry").news.mean()
    print("share of stock-days flagged as news: normal-type", round(news_share.get(0.0, np.nan), 3),
          "monthly expiry", round(news_share.get(1.0, np.nan), 3))
    return out


def by_expiry(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional slope of the next morning's return on the window's move, per session.

    Within a session the session effect is a constant, so each session's slope is the
    within-session regression with a security effect approximated by the security's mean.
    """
    rows = []
    frame = panel[panel.group.isin(GROUP_SETS["derivative"] + ["placebo"])].copy()
    frame["set"] = np.where(frame.group == "placebo", "placebo", "derivative")
    for (session, kind, s), block in frame.groupby(["session", "day_type", "set"]):
        b = block[["drift", "next_rev"]].dropna()
        if len(b) < 20 or b.drift.var() == 0:
            continue
        x, y = b.drift - b.drift.mean(), b.next_rev - b.next_rev.mean()
        rows.append({"session": session, "day_type": kind, "set": s,
                     "slope": float((x * y).sum() / (x * x).sum()), "n": len(b)})
    return pd.DataFrame(rows)


def session_ri(slopes: pd.DataFrame, draws: int = 10_000, seed: int = 20220127
               ) -> pd.DataFrame:
    """Mean slope over the twelve expiries against means over one ordinary session a month."""
    rng = np.random.default_rng(seed)
    rows = []
    for s, block in slopes.groupby("set"):
        block = block.assign(month=block.session.str[2:4])
        expiry = block[block.day_type == "monthly_expiry"].slope.mean()
        normal = block[block.day_type == "normal"]
        by_month = [g.slope.to_numpy() for _, g in normal.groupby("month")]
        sims = np.array([np.mean([m[rng.integers(len(m))] for m in by_month])
                         for _ in range(draws)])
        rows.append({"set": s, "expiry_mean": expiry, "normal_mean": normal.slope.mean(),
                     "ri_p": float(np.mean(np.abs(sims - sims.mean())
                                           >= abs(expiry - sims.mean())))})
    return pd.DataFrame(rows)


def path_by_news(panel: pd.DataFrame) -> pd.DataFrame:
    """Figure 2's path, the window move and the next morning, with news days removed."""
    rows = []
    for news_free in (False, True):
        frame = panel[~panel.news.fillna(False)] if news_free else panel
        settle = frame.drift - frame.groupby("session").drift.transform("mean")
        sign = np.sign(settle)
        points = {
            "settle": settle,
            "next_open": (frame.drift + frame.gap),
            "next_open30": (frame.drift + frame.next_rev),
            "next_close": (frame.drift + frame.next_day),
        }
        for name, v in points.items():
            v = v - v.groupby(frame.session).transform("mean")
            tmp = pd.DataFrame({"v": v * sign, "group": frame.group, "kind": frame.day_type})
            g = tmp.groupby(["group", "kind"]).v.agg(["mean", "sem", "count"]).reset_index()
            g["point"], g["news_free"] = name, news_free
            rows.append(g)
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    panel = load()
    out = Path(RESULTS_DIR)
    table = robustness_table(panel)
    table.to_csv(out / "s11_overnight_robustness.csv", index=False)
    slopes = by_expiry(panel)
    slopes.to_csv(out / "s11_overnight_by_session.csv", index=False)
    ri = session_ri(slopes)
    ri.to_csv(out / "s11_overnight_session_ri.csv", index=False)
    print(ri.round(3).to_string(index=False))
    path_by_news(panel).to_csv(out / "s11_overnight_path.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(table[["sample", "spec", "base", "expiry", "expiry_se", "expiry_p", "nobs"]]
              .round(3).to_string(index=False))


if __name__ == "__main__":
    main()
