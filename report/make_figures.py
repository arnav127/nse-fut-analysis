"""Figures for the project course report that are not already in paper/figures.

Run from the repository root: python report/make_figures.py
Reads the result tables in data/results and writes PDFs to report/figures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stage9_tape.followups import WINDOW_MIN, book_paired  # noqa: E402

RES = ROOT / "data" / "results"
FIG = ROOT / "report" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, GREY, LIGHT = "#1f4e79", "#c55a11", "#8c8c8c", "#5b9bd5"
GROUP_COLOUR = {"liquid": BLUE, "illiquid": LIGHT, "placebo": GREY}
GROUP_LABEL = {"liquid": "Liquid F&O", "illiquid": "Illiquid F&O", "placebo": "Placebo (no F&O)"}

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
                     "savefig.bbox": "tight", "legend.frameon": False})


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def primary_tests():
    """The four main tests: expiry against the day before, with the paired p-value."""
    tests = [
        ("BH1\nSettlement VWAP vs\n15:00 mid (bps)", 34.48, 36.01, "p = 0.21"),
        ("BH2\nQuoted spread\n(bps)", 5.29, 5.60, "p < 0.001"),
        ("BH3\n|Order imbalance|\n(x100)", 14.7, 14.9, "p = 0.54"),
        ("BH4\nOrders cancelled\nwithin 1 s (%)", 28.65, 30.03, "p < 0.001"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(10, 3.0))
    for ax, (label, control, expiry, p) in zip(axes, tests):
        ax.bar([0, 1], [control, expiry], color=[BLUE, ORANGE], width=0.6)
        ax.set_xticks([0, 1], ["Day before", "Expiry"])
        ax.set_title(label, fontsize=8.5)
        ax.set_ylim(min(control, expiry) * 0.85, max(control, expiry) * 1.08)
        rejected = "<" in p
        ax.text(0.5, max(control, expiry) * 1.03, p, ha="center", fontsize=8.5,
                fontweight="bold" if rejected else "normal",
                color=ORANGE if rejected else "#333333")
        ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, "primary_tests")


def placebo_check():
    d = pd.read_csv(RES / "s17_placebo_check.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2), gridspec_kw={"width_ratios": [2, 1]})
    rng = np.random.default_rng(0)
    for i, g in enumerate(["liquid", "illiquid", "placebo"]):
        r = d[d.group == g]["rank"].dropna()
        axes[0].scatter(r, i + rng.uniform(-0.18, 0.18, len(r)), s=12, alpha=0.7,
                        color=GROUP_COLOUR[g])
        axes[0].plot([r.median()] * 2, [i - 0.3, i + 0.3], color="black", linewidth=1.5)
    axes[0].axvline(500, color=ORANGE, linestyle="--", linewidth=1)
    axes[0].text(330, 2.45, "turnover rank 500", color=ORANGE, fontsize=8)
    axes[0].set_yticks(range(3), [GROUP_LABEL[g] for g in ["liquid", "illiquid", "placebo"]])
    axes[0].set_xlabel("rank by turnover among 1,129 traded stocks (1 = most traded)")
    axes[0].set_title("Where each stock ranks (black bar = median)", fontsize=9)
    counts = d.groupby("group").n500_2022oct.sum().reindex(["liquid", "illiquid", "placebo"])
    axes[1].bar(range(3), counts, color=[GROUP_COLOUR[g] for g in counts.index])
    for i, v in enumerate(counts):
        axes[1].text(i, v + 0.8, f"{int(v)}/50", ha="center", fontsize=8.5)
    axes[1].set_xticks(range(3), ["Liquid", "Illiquid", "Placebo"])
    axes[1].set_ylim(0, 56)
    axes[1].set_title("In the Nifty 500 (Oct 2022)", fontsize=9)
    fig.tight_layout()
    save(fig, "placebo_check")


def volatility_scatter():
    book = pd.read_parquet(RES / "book_profile.parquet")
    d = book_paired(book, WINDOW_MIN, 375).dropna()
    d["set"] = np.where(d.group == "placebo", "placebo", "fo")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    for ax, y, title in ((axes[0], "d_spread", "Change in quoted spread (%)"),
                         (axes[1], "d_depth", "Change in displayed depth (%)")):
        for s, colour, label in (("fo", BLUE, "F&O stocks"), ("placebo", GREY, "Placebo stocks")):
            sub = d[d.set == s]
            bins = pd.qcut(sub.d_rv, 15, duplicates="drop")
            g = sub.groupby(bins, observed=True)[["d_rv", y]].mean()
            ax.scatter(g.d_rv, g[y], color=colour, s=22, label=label, zorder=3)
            b = np.polyfit(sub.d_rv, sub[y], 1)
            xs = np.linspace(g.d_rv.min(), g.d_rv.max(), 50)
            ax.plot(xs, np.polyval(b, xs), color=colour, linewidth=1)
        ax.axhline(0, color="#333333", linewidth=0.6)
        ax.axvline(0, color="#333333", linewidth=0.6)
        ax.set_xlabel("change in volatility of the mid, expiry vs day before (%)")
        ax.set_title(title, fontsize=9)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig, "volatility_scatter")


def panel_coefficients():
    p = pd.read_csv(RES / "s16_bh2_panel.csv")
    p = p[p.part == "window"]
    order = [("liquid", "Liquid F&O"), ("illiquid", "Illiquid F&O"), ("placebo", "Placebo"),
             ("did", "F&O minus placebo")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.0), sharey=True)
    for ax, y, title in ((axes[0], "log_spread", "Window quoted spread"),
                         (axes[1], "log_depth", "Window displayed depth")):
        for k, (ctrl, colour, lab) in enumerate(((False, BLUE, "no control"),
                                                (True, ORANGE, "controlling for volatility"))):
            sub = p[(p.y == y) & (p.vol_control == ctrl)].set_index("sample")
            yy = np.arange(len(order)) + (0.15 if k == 0 else -0.15)
            coef = [sub.loc[s, "coef"] for s, _ in order]
            se = [sub.loc[s, "se"] for s, _ in order]
            ax.errorbar(coef, yy, xerr=1.96 * np.array(se), fmt="o", color=colour,
                        capsize=2, label=lab)
        ax.axvline(0, color="#333333", linewidth=0.6)
        ax.set_yticks(range(len(order)), [l for _, l in order])
        ax.invert_yaxis()
        ax.set_xlabel("expiry-day effect (%), 95% interval")
        ax.set_title(title, fontsize=9)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig, "panel_coefficients")


def positions():
    pos = pd.read_csv(RES / "s18_positions.csv")
    med = pos.groupby("who")[["fut_net_before", "call_net_before", "put_net_before"]
                             ].median() / 1e3
    med = med.reindex(["FII", "DII", "Pro", "Client"])
    fig, ax = plt.subplots(figsize=(9, 3.2))
    x = np.arange(len(med))
    for k, (col, colour, lab) in enumerate((("fut_net_before", GREY, "Index futures"),
                                            ("call_net_before", BLUE, "Index calls"),
                                            ("put_net_before", ORANGE, "Index puts"))):
        ax.bar(x + (k - 1) * 0.26, med[col], 0.26, color=colour, label=lab)
    ax.axhline(0, color="#333333", linewidth=0.6)
    ax.set_xticks(x, ["Foreign institutions", "Domestic institutions", "Proprietary",
                      "Clients"])
    ax.set_ylabel("net position, thousand contracts\n(long minus short)")
    ax.set_title("Index derivatives positions on the day before an index expiry (median of 52)",
                 fontsize=9)
    ax.legend(fontsize=8, ncol=3)
    fig.tight_layout()
    save(fig, "positions")


def oi_scatter():
    oi = pd.read_csv(RES / "s18_expiring_oi.csv", dtype={"session": str})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    for ax, x, label, scale in ((axes[0], "opt_oi_cr", "expiring Nifty option OI (lakh crore notional)", 1e5),
                                (axes[1], "pcr", "put-call ratio of expiring OI", 1)):
        colours = np.where(oi.monthly == 1, ORANGE, BLUE)
        ax.scatter(oi[x] / scale, oi.rel_drift, c=colours, s=18)
        b = np.polyfit(oi[x] / scale, oi.rel_drift, 1)
        xs = np.linspace((oi[x] / scale).min(), (oi[x] / scale).max(), 20)
        ax.plot(xs, np.polyval(b, xs), color="#333333", linewidth=1)
        ax.axhline(0, color="#333333", linewidth=0.6)
        ax.set_xlabel(label)
    axes[0].set_ylabel("Nifty 50 minus Next 50,\nwindow move (bps)")
    axes[0].scatter([], [], color=BLUE, s=18, label="weekly expiry")
    axes[0].scatter([], [], color=ORANGE, s=18, label="monthly expiry")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig, "oi_scatter")


def flows():
    c = pd.read_csv(RES / "s18_cash_flows.csv")
    labels = {"flow": "All", "flow_custodian": "Custodian\n(institutions)",
              "flow_proprietary": "Proprietary", "flow_ncnp": "Other clients"}
    samples = [("Nifty 50 stocks", BLUE), ("other F&O stocks", LIGHT), ("placebo", GREY)]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    x = np.arange(len(labels))
    for k, (s, colour) in enumerate(samples):
        sub = c[c["sample"] == s].set_index("y").reindex(list(labels))
        ax.bar(x + (k - 1) * 0.26, sub.coef, 0.26, yerr=1.96 * sub.se, color=colour,
               capsize=2, label=s if s != "placebo" else "Placebo stocks")
    ax.axhline(0, color="#333333", linewidth=0.6)
    ax.set_xticks(x, list(labels.values()))
    ax.set_ylabel("change in net aggressive buying\n(% of median daily volume)")
    ax.set_title("Net buying in the settlement window on index expiries vs other days, by who "
                 "initiates the trade", fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save(fig, "index_flows")


def index_deriv():
    d = pd.read_csv(RES / "s18_index_deriv_flows.csv", dtype={"session": str})
    w = d[d.in_window & d.expiring & d.kind.isin(["calls", "puts"])]
    m = w.groupby(["kind", "is_expiry"])[["net_aggressor", "prop_net"]].mean() / 1e5
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.0), sharey=True)
    for ax, col, title in ((axes[0], "net_aggressor", "Net aggressive buying (all traders)"),
                           (axes[1], "prop_net", "Net buying by proprietary traders")):
        for k, (flag, colour, lab) in enumerate(((False, BLUE, "Day before"),
                                                (True, ORANGE, "Expiry day"))):
            vals = [m.loc[(kind, flag), col] for kind in ("calls", "puts")]
            ax.bar(np.arange(2) + (k - 0.5) * 0.35, vals, 0.35, color=colour, label=lab)
        ax.axhline(0, color="#333333", linewidth=0.6)
        ax.set_xticks(range(2), ["Expiring calls", "Expiring puts"])
        ax.set_title(title, fontsize=9)
    axes[0].set_ylabel("lakh units, 15:00 to 15:30")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig, "index_deriv")


def futures_compare():
    f = pd.read_csv(RES / "s13_futures_book.csv")
    f = f[f.part == "15:00-15:30"]
    measures = [("d_spread", "Quoted spread"), ("d_depth", "Depth"), ("d_rv", "Volatility")]
    fig, ax = plt.subplots(figsize=(7, 3.0))
    x = np.arange(len(measures))
    for k, (market, colour, lab) in enumerate((("cash", BLUE, "Cash market"),
                                              ("futures", ORANGE, "Expiring stock future"))):
        sub = f[f.market == market].set_index("measure")
        vals = [sub.loc[m, "mean"] for m, _ in measures]
        ax.bar(x + (k - 0.5) * 0.35, vals, 0.35, color=colour, label=lab)
        for i, v in enumerate(vals):
            ax.text(x[i] + (k - 0.5) * 0.35, v + (1.5 if v >= 0 else -4), f"{v:+.0f}%",
                    ha="center", fontsize=8)
    ax.axhline(0, color="#333333", linewidth=0.6)
    ax.set_xticks(x, [l for _, l in measures])
    ax.set_ylabel("expiry vs day before (%)")
    ax.set_title("Settlement window, 12 monthly expiries", fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save(fig, "futures_compare")


def futures_roll():
    t = pd.read_csv(RES / "s13_futures_tape.csv").set_index(["contract", "measure"])
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    days = ["Day before expiry", "Expiry day"]
    near = [t.loc[("near", "contract_share"), "control"], t.loc[("near", "contract_share"), "expiry"]]
    nxt = [t.loc[("next", "contract_share"), "control"], t.loc[("next", "contract_share"), "expiry"]]
    ax.bar(days, near, color=ORANGE, label="Expiring contract")
    ax.bar(days, nxt, bottom=near, color=BLUE, label="Next month's contract")
    for i in range(2):
        ax.text(i, near[i] / 2, f"{near[i]:.0f}%", ha="center", color="white", fontsize=9)
        ax.text(i, near[i] + nxt[i] / 2, f"{nxt[i]:.0f}%", ha="center", color="white",
                fontsize=9)
    ax.set_ylabel("share of stock futures volume (%)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, "futures_roll")


if __name__ == "__main__":
    for f in (primary_tests, placebo_check, volatility_scatter, panel_coefficients, positions,
              oi_scatter, flows, index_deriv, futures_compare, futures_roll):
        f()
        print("ok", f.__name__)
