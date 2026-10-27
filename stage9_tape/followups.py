"""Analyses and figures for the action items of the 21 October meeting.

  BH2   spread and depth through the whole session on expiry and control days, in cash and
        in the expiring stock future; whether the widening follows the rise in volatility
  BH3   futures: where the volume sits (roll), and imbalance in the window
  BH4   whether the rise in fleeting orders follows the rise in volatility
  Fig 2 the next-morning reversal against news (from overnight_tests)

Inputs: book_profile.parquet, futures_book/, s12_futures_tape.csv, a12_order_lifespan.csv,
s11_overnight_*.csv. Figures go to notes/figures/, numbers to data/results/s13_followups.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import EXPIRY_CONTROL_PAIRS, PAPER_FIGURES_DIR, RESULTS_DIR  # noqa: E402

RES = Path(RESULTS_DIR)
FIG = PROJECT_ROOT / "notes" / "figures"
EXPIRY, CONTROL = "#c55a11", "#1f4e79"
GROUPS = ["liquid", "illiquid", "placebo"]
GROUP_LABEL = {"liquid": "Liquid F&O", "illiquid": "Illiquid F&O", "placebo": "Placebo (no F&O)"}
WINDOW_MIN = 345          # minutes from 09:15 to 15:00
NUMBERS: dict = {}
PAIR_OF = {c: e for e, c in EXPIRY_CONTROL_PAIRS} | {e: e for e, _ in EXPIRY_CONTROL_PAIRS}


def _save(fig, name: str) -> None:
    for folder in (FIG, Path(PAPER_FIGURES_DIR)):
        folder.mkdir(parents=True, exist_ok=True)
        fig.savefig(folder / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def _clock(minutes):
    return [f"{(9 * 60 + 15 + m) // 60:02d}:{(9 * 60 + 15 + m) % 60:02d}" for m in minutes]


def _ttest(x: pd.Series) -> dict:
    x = x.dropna()
    t = stats.ttest_1samp(x, 0.0)
    return {"mean": float(x.mean()), "se": float(x.std(ddof=1) / np.sqrt(len(x))),
            "p": float(t.pvalue), "n": int(len(x))}


# --- BH2: the book through the day --------------------------------------------------------

def book_paired(book: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    """Per security and month: log ratio of expiry to control over minutes [lo, hi)."""
    part = book[(book.minute >= lo) & (book.minute < hi)]
    agg = part.groupby(["symbol", "group", "session", "is_expiry"]).agg(
        spread=("spread_bps", "mean"), depth=("depth_cr", "mean"), rv=("rv_bps2", "mean")
    ).reset_index()
    agg["pair"] = agg.session.map(PAIR_OF)
    wide = agg.pivot_table(index=["symbol", "group", "pair"], columns="is_expiry",
                           values=["spread", "depth", "rv"])
    out = pd.DataFrame(index=wide.index)
    for v in ("spread", "depth", "rv"):
        out[f"d_{v}"] = 100 * np.log(wide[(v, True)] / wide[(v, False)])
    return out.replace([np.inf, -np.inf], np.nan).reset_index()


def figure_book_day(book: pd.DataFrame, value: str, label: str, name: str,
                    log: bool = False) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=False)
    for ax, g in zip(axes, GROUPS):
        sub = book[book.group == g]
        for flag, colour, lab in ((False, CONTROL, "Day before"), (True, EXPIRY, "Expiry day")):
            s = sub[sub.is_expiry == flag].groupby("minute")[value].median()
            s = s.rolling(5, center=True, min_periods=1).mean()
            ax.plot(s.index, s.values, color=colour, linewidth=1.1, label=lab)
        ax.axvspan(WINDOW_MIN, 375, color="#eeeeee", zorder=0)
        ax.set_title(GROUP_LABEL[g], fontsize=10)
        ticks = [0, 105, 225, 345]
        ax.set_xticks(ticks, _clock(ticks), fontsize=8)
        if log:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
            ax.yaxis.set_minor_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
            ax.tick_params(axis="y", which="minor", labelsize=7)
        ax.grid(alpha=0.25, linewidth=0.5)
    axes[0].set_ylabel(label)
    axes[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    _save(fig, name)


def figure_window_zoom(book: pd.DataFrame) -> None:
    """The last hour, minute by minute: F&O stocks against the placebo group."""
    book = book[book.minute >= WINDOW_MIN - 30].copy()
    book["set"] = np.where(book.group == "placebo", "placebo", "fo")
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.2), sharex=True)
    for col, (s, title) in enumerate((("fo", "F&O stocks"), ("placebo", "Placebo stocks"))):
        sub = book[book.set == s]
        for row, (value, label) in enumerate((("spread_bps", "Quoted spread (bps)"),
                                              ("depth_cr", "Depth, 5 levels (Rs crore)"))):
            ax = axes[row, col]
            for flag, colour, lab in ((False, CONTROL, "Day before"),
                                      (True, EXPIRY, "Expiry day")):
                m = sub[sub.is_expiry == flag].groupby("minute")[value].median()
                ax.plot(m.index, m.values, color=colour, marker="o", markersize=2.5,
                        linewidth=1.1, label=lab)
            ax.axvspan(WINDOW_MIN, 375, color="#eeeeee", zorder=0)
            ax.grid(alpha=0.25, linewidth=0.5)
            ticks = list(range(WINDOW_MIN - 30, 376, 10))
            ax.set_xticks(ticks, _clock(ticks), fontsize=8)
            if row == 0:
                ax.set_title(title, fontsize=10)
            if col == 0:
                ax.set_ylabel(label)
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    _save(fig, "bh2_window_zoom")


def figure_book_ratio(book: pd.DataFrame) -> pd.DataFrame:
    """Expiry minus control, in log points, by half hour of the session and group."""
    rows = []
    for lo in range(0, 375, 15):
        d = book_paired(book, lo, lo + 15)
        for g in GROUPS:
            for v in ("d_spread", "d_depth"):
                r = _ttest(d.loc[d.group == g, v])
                rows.append({"start": lo, "group": g, "measure": v, **r})
    frame = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    colour = {"liquid": "#1f4e79", "illiquid": "#5b9bd5", "placebo": "#9a9a9a"}
    for ax, v, title in ((axes[0], "d_spread", "Quoted spread"),
                         (axes[1], "d_depth", "Displayed depth (5 levels)")):
        for g in GROUPS:
            s = frame[(frame.group == g) & (frame.measure == v)]
            x = s.start + 7.5
            ax.plot(x, s["mean"], marker="o", markersize=3, color=colour[g], label=GROUP_LABEL[g])
            ax.fill_between(x, s["mean"] - 1.96 * s.se, s["mean"] + 1.96 * s.se,
                            color=colour[g], alpha=0.12)
        ax.axhline(0, color="#333333", linewidth=0.6)
        ax.axvspan(WINDOW_MIN, 375, color="#eeeeee", zorder=0)
        ticks = [0, 105, 225, 345]
        ax.set_xticks(ticks, _clock(ticks), fontsize=8)
        ax.set_title(f"{title}: expiry vs day before (%)", fontsize=10)
        ax.grid(alpha=0.25, linewidth=0.5)
    axes[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    _save(fig, "bh2_ratio_by_time")
    return frame


def volatility_test(book: pd.DataFrame) -> pd.DataFrame:
    """Is the widening in the window explained by the rise in volatility?

    Regress the expiry-minus-control change in log spread (and depth) on the change in log
    realised variance, across securities and months. The intercept is the change that a
    security whose volatility did not change would show.
    """
    d = book_paired(book, WINDOW_MIN, 375).dropna()
    rows = []
    for g in ["all F&O", *GROUPS]:
        sub = d[d.group.isin(["liquid", "illiquid"])] if g == "all F&O" else d[d.group == g]
        if len(sub) < 10:
            continue
        for v in ("d_spread", "d_depth"):
            raw = _ttest(sub[v])
            X = np.column_stack([np.ones(len(sub)), sub.d_rv])
            beta, *_ = np.linalg.lstsq(X, sub[v], rcond=None)
            resid = sub[v] - X @ beta
            cov = np.linalg.inv(X.T @ X) * resid.var(ddof=2)
            se = np.sqrt(np.diag(cov))
            rows.append({"group": g, "measure": v, "raw_mean": raw["mean"], "raw_p": raw["p"],
                         "d_rv_mean": float(sub.d_rv.mean()), "slope_rv": beta[1],
                         "slope_se": se[1], "intercept": beta[0], "intercept_se": se[0],
                         "intercept_p": float(2 * stats.t.sf(abs(beta[0] / se[0]), len(sub) - 2)),
                         "n": len(sub)})
    return pd.DataFrame(rows)


# --- futures ------------------------------------------------------------------------------

def futures_book_figures() -> pd.DataFrame:
    files = sorted((RES / "futures_book").glob("session=*.parquet"))
    if not files:
        return pd.DataFrame()
    fb = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4), sharex=True)
    for col, market in enumerate(("cash", "futures")):
        sub = fb[fb.market == market]
        for row, (value, label) in enumerate((("spread_bps", "Quoted spread (bps)"),
                                              ("depth_cr", "Depth, 5 levels (Rs crore)"))):
            ax = axes[row, col]
            for flag, colour, lab in ((False, CONTROL, "Day before"),
                                      (True, EXPIRY, "Expiry day")):
                s = sub[sub.is_expiry == flag].groupby("minute")[value].median()
                s = s.rolling(5, center=True, min_periods=1).mean()
                ax.plot(s.index, s.values, color=colour, linewidth=1.1, label=lab)
            ax.axvspan(WINDOW_MIN, 375, color="#eeeeee", zorder=0)
            ax.grid(alpha=0.25, linewidth=0.5)
            if row == 0:
                ax.set_title("Cash" if market == "cash" else "Expiring stock future", fontsize=10)
            if col == 0:
                ax.set_ylabel(label)
            ticks = [0, 105, 225, 345]
            ax.set_xticks(ticks, _clock(ticks), fontsize=8)
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    _save(fig, "futures_book_day")

    rows = []
    for market in ("cash", "futures"):
        sub = fb[fb.market == market].copy()
        sub["group"] = "fo"
        for lo, hi, part in ((15, WINDOW_MIN, "09:30-15:00"), (WINDOW_MIN, 375, "15:00-15:30")):
            d = book_paired(sub, lo, hi)
            for v in ("d_spread", "d_depth", "d_rv"):
                rows.append({"market": market, "part": part, "measure": v, **_ttest(d[v])})
    # The same volatility regression as for the cash market, on the expiring future's window.
    fut = fb[fb.market == "futures"].assign(group="liquid")  # pooled under one label
    test = volatility_test(fut[["symbol", "group", "session", "is_expiry", "minute",
                                "spread_bps", "depth_cr", "rv_bps2"]])
    test[test.group == "all F&O"].to_csv(RES / "s13_futures_voltest.csv", index=False)
    return pd.DataFrame(rows)


def futures_tape() -> pd.DataFrame:
    d = pd.read_csv(RES / "s12_futures_tape.csv", dtype={"session": str})
    d["oib"] = (d.window_bi - d.window_si) / (d.window_bi + d.window_si)
    d["abs_oib"] = d.oib.abs()
    d["window_share"] = 100 * d.window_volume / d.volume
    d["abs_move"] = (1e4 * np.log(d.last1_vwap / d.first1_vwap)).abs()
    total = d.groupby(["symbol", "session"]).volume.transform("sum")
    d["contract_share"] = 100 * d.volume / total
    d["pair"] = d.session.map(PAIR_OF)
    rows = []
    for contract in ("near", "next"):
        sub = d[d.contract == contract]
        wide = sub.pivot_table(index=["symbol", "pair"], columns="is_expiry",
                               values=["abs_oib", "window_share", "abs_move", "contract_share"])
        for v in ("abs_oib", "window_share", "abs_move", "contract_share"):
            diff = (wide[(v, True)] - wide[(v, False)]).dropna()
            rows.append({"contract": contract, "measure": v,
                         "control": float(wide[(v, False)].mean()),
                         "expiry": float(wide[(v, True)].mean()), **_ttest(diff)})
    return pd.DataFrame(rows)


# --- BH4: fleeting orders and volatility --------------------------------------------------

def fleeting_vs_volatility(book: pd.DataFrame) -> pd.DataFrame:
    life = pd.read_csv(RES / "a12_order_lifespan.csv")
    life = life[life.phantom_order_rate > 0]
    life["entered"] = life.phantom_orders / life.phantom_order_rate
    agg = life.groupby(["symbol", "trade_date", "is_expiry"]).agg(
        phantom=("phantom_orders", "sum"), entered=("entered", "sum")).reset_index()
    agg["rate"] = agg.phantom / agg.entered
    agg["session"] = pd.to_datetime(agg.trade_date).dt.strftime("%d%m%Y")
    agg["pair"] = agg.session.map(PAIR_OF)
    wide = agg.pivot_table(index=["symbol", "pair"], columns="is_expiry", values="rate")
    d_rate = (100 * (wide[True] - wide[False])).rename("d_rate").reset_index()
    vol = book_paired(book, WINDOW_MIN, 375)[["symbol", "group", "pair", "d_rv", "d_spread"]]
    d = d_rate.merge(vol, on=["symbol", "pair"]).dropna()
    rows = []
    for g in ["all", "liquid", "illiquid", "placebo"]:
        sub = d if g == "all" else d[d.group == g]
        X = np.column_stack([np.ones(len(sub)), sub.d_rv])
        beta, *_ = np.linalg.lstsq(X, sub.d_rate, rcond=None)
        resid = sub.d_rate - X @ beta
        se = np.sqrt(np.diag(np.linalg.inv(X.T @ X) * resid.var(ddof=2)))
        rows.append({"group": g, "raw_mean_pp": float(sub.d_rate.mean()),
                     "slope_rv": beta[1], "slope_se": se[1], "intercept_pp": beta[0],
                     "intercept_se": se[0], "corr": float(sub.d_rate.corr(sub.d_rv)),
                     "n": len(sub)})
    return pd.DataFrame(rows)


# --- Figure 2 and news ----------------------------------------------------------------------

def figure_overnight() -> None:
    slopes = pd.read_csv(RES / "s11_overnight_by_session.csv", dtype={"session": str})
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, s in zip(axes, ("derivative", "placebo")):
        sub = slopes[slopes.set == s]
        normal = sub[sub.day_type == "normal"].slope
        exp = sub[sub.day_type == "monthly_expiry"].sort_values("session",
                                                                key=lambda x: x.str[4:] + x.str[2:4])
        ax.hist(normal, bins=30, color="#bbbbbb", density=True, label="Ordinary sessions")
        for _, r in exp.iterrows():
            ax.axvline(r.slope, color=EXPIRY, linewidth=1.0, alpha=0.8)
        ax.axvline(np.nan, color=EXPIRY, label="Each monthly expiry")
        top = ax.get_ylim()[1]
        for i, (_, r) in enumerate(exp[exp.slope.abs() > 0.5].sort_values("slope").iterrows()):
            ax.text(r.slope, top * (0.55 - 0.18 * (i % 2)),
                    pd.to_datetime(r.session, format="%d%m%Y").strftime("%d %b"),
                    rotation=90, fontsize=7, ha="right", va="top", color=EXPIRY)
        ax.set_title(("F&O stocks" if s == "derivative" else "Placebo stocks")
                     + ": next-morning return on window move", fontsize=10)
        ax.set_xlabel("slope (negative = window move reversed)")
        ax.legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    _save(fig, "overnight_by_expiry")

    rob = pd.read_csv(RES / "s11_overnight_robustness.csv")
    specs = ["baseline", "without news days", "beta-adjusted", "without 24 Feb 2022",
             "beta-adjusted, without news days"]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for i, (s, colour) in enumerate((("derivative", "#1f4e79"), ("placebo", "#9a9a9a"))):
        sub = rob[(rob["sample"] == s)].set_index("spec").loc[specs]
        y = np.arange(len(specs)) + (0.18 if i == 0 else -0.18)
        ax.errorbar(sub.expiry, y, xerr=1.96 * sub.expiry_se, fmt="o", color=colour,
                    capsize=2, label="F&O stocks" if s == "derivative" else "Placebo")
    ax.axvline(0, color="#333333", linewidth=0.6)
    ax.set_yticks(np.arange(len(specs)), specs, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("extra reversal on monthly expiries (coef. on window move x expiry)")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    _save(fig, "overnight_robustness")


def main() -> None:
    out = {}
    book_path = RES / "book_profile.parquet"
    if book_path.exists():
        book = pd.read_parquet(book_path)
        figure_book_day(book, "spread_bps", "Quoted spread (bps)", "bh2_spread_day", log=True)
        figure_book_day(book, "depth_cr", "Depth, 5 levels (Rs crore)", "bh2_depth_day",
                        log=True)
        figure_window_zoom(book)
        ratio = figure_book_ratio(book)
        ratio.to_csv(RES / "s13_book_ratio.csv", index=False)
        vt = volatility_test(book)
        vt.to_csv(RES / "s13_volatility_test.csv", index=False)
        fl = fleeting_vs_volatility(book)
        fl.to_csv(RES / "s13_fleeting_volatility.csv", index=False)
        whole = []
        for lo, hi, part in ((15, WINDOW_MIN, "09:30-15:00"), (WINDOW_MIN, 375, "15:00-15:30")):
            d = book_paired(book, lo, hi)
            for g in GROUPS:
                for v in ("d_spread", "d_depth", "d_rv"):
                    whole.append({"part": part, "group": g, "measure": v,
                                  **_ttest(d.loc[d.group == g, v])})
        pd.DataFrame(whole).to_csv(RES / "s13_book_parts.csv", index=False)
        with pd.option_context("display.width", 200):
            print(pd.DataFrame(whole).round(3).to_string(index=False))
            print(vt.round(3).to_string(index=False))
            print(fl.round(3).to_string(index=False))
    fut = futures_book_figures()
    if not fut.empty:
        fut.to_csv(RES / "s13_futures_book.csv", index=False)
        print(fut.round(3).to_string(index=False))
    ft = futures_tape()
    ft.to_csv(RES / "s13_futures_tape.csv", index=False)
    print(ft.round(3).to_string(index=False))
    figure_overnight()


if __name__ == "__main__":
    main()
