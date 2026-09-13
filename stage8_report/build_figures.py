"""The report's figures.

One figure per argument the results section makes, written where that argument is made rather
than collected at the end of the document. A figure the reader has to leaf forward to is a
figure they do not look at.

Everything is PDF: the document is LaTeX, and vector output at the size these are reproduced
at is both smaller and sharper than a raster at any sensible resolution.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config.settings import PAPER_FIGURES_DIR, RESULTS_DIR  # noqa: E402
from stage6_insights.s4_marking_cost import PROBE_NOTIONAL_CR  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Figures", "stage8_report.log")

EXPIRY_COLOUR = "#1f4e79"
CONTROL_COLOUR = "#9a9a9a"
GROUP_ORDER = ["liquid", "illiquid", "placebo"]
GROUP_LABEL = {"liquid": "Liquid (F\\&O)", "illiquid": "Illiquid (F\\&O)",
               "placebo": "Placebo (no F\\&O)"}


def _style() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        # Text in the figures is set by matplotlib, not LaTeX, so group labels must not
        # carry TeX escapes.
        "text.usetex": False,
    })


def _label(key: str) -> str:
    return GROUP_LABEL.get(key, key).replace("\\&", "&")


def _read(name: str) -> pd.DataFrame:
    path = Path(RESULTS_DIR) / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _save(fig, name: str) -> None:
    Path(PAPER_FIGURES_DIR).mkdir(parents=True, exist_ok=True)
    fig.savefig(Path(PAPER_FIGURES_DIR) / name)
    plt.close(fig)
    logger.info(f"[FIGURE] {name}")


def _paired_bars(ax, frame: pd.DataFrame, column: str, title: str, ylabel: str) -> None:
    """Expiry against control, side by side, for each group present."""
    groups = [g for g in GROUP_ORDER if g in set(frame.get("security_group", []))]
    if not groups:
        return
    width = 0.36
    positions = np.arange(len(groups))
    for offset, flag, colour, label in ((-width / 2, False, CONTROL_COLOUR, "Control"),
                                        (width / 2, True, EXPIRY_COLOUR, "Expiry")):
        heights = []
        for group in groups:
            subset = frame[(frame.security_group == group) & (frame.is_expiry.astype(bool) == flag)]
            values = pd.to_numeric(subset[column], errors="coerce")
            heights.append(values.median() if len(values) else np.nan)
        ax.bar(positions + offset, heights, width, color=colour, label=label)
    ax.set_xticks(positions)
    ax.set_xticklabels([_label(g) for g in groups])
    ax.set_title(title)
    ax.set_ylabel(ylabel)


def _distribution(ax, frame: pd.DataFrame, column: str, title: str,
                  reference: Optional[float] = None) -> None:
    """Overlapping histograms, expiry against control."""
    values = pd.to_numeric(frame.get(column), errors="coerce")
    flag = frame.is_expiry.astype(bool)
    clean = pd.DataFrame({"v": values, "e": flag}).replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        ax.set_visible(False)
        return
    # A shared, trimmed range: one outlier otherwise compresses both distributions into the
    # leftmost bin and the figure shows nothing.
    low, high = clean.v.quantile([0.01, 0.99])
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        low, high = clean.v.min(), clean.v.max()
    bins = np.linspace(low, high, 28)
    for is_expiry, colour, label in ((False, CONTROL_COLOUR, "Control"),
                                     (True, EXPIRY_COLOUR, "Expiry")):
        ax.hist(clean.loc[clean.e == is_expiry, "v"], bins=bins, alpha=0.6,
                color=colour, label=label, density=True)
    if reference is not None:
        ax.axvline(reference, color="#b00020", linestyle="--", linewidth=1)
    ax.set_title(title)
    ax.set_yticks([])


def figure_marking_cost() -> None:
    frame = _read("s4_marking_cost.csv")
    tag = f"{PROBE_NOTIONAL_CR[0]:g}".replace(".", "p")
    if frame.empty or f"move_bps_{tag}" not in frame.columns:
        return
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    _paired_bars(axes[0], frame, f"move_bps_{tag}",
                 f"Price move from sweeping {PROBE_NOTIONAL_CR[0]} cr", "basis points")
    _paired_bars(axes[1], frame, "visible_notional_cr",
                 "Displayed notional in the book", "crore")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    _save(fig, "marking_cost.pdf")


def figure_pressure() -> None:
    frame = _read("s2_pressure_or_activity.csv")
    if frame.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 2.6))
    _distribution(axes[0], frame, "variance_ratio",
                  "Variance ratio (60s / 1s)", reference=1.0)
    _distribution(axes[1], frame, "flow_autocorr",
                  "Signed flow autocorrelation", reference=0.0)
    _distribution(axes[2], frame, "permanent_share", "Permanent share of impact")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("density")
    fig.tight_layout()
    _save(fig, "pressure_measures.pdf")


def figure_settlement() -> None:
    frame = _read("s1_settlement_price.csv")
    if frame.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 2.6))
    _distribution(axes[0], frame, "abs_drift_bps", "|Settlement VWAP - open mid|")
    _distribution(axes[1], frame, "abs_reversal_bps", "|Settlement VWAP - close|")
    _distribution(axes[2], frame, "terminal_gap_bps", "|Final minute - window VWAP|")
    for ax in axes:
        ax.set_xlabel("basis points")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("density")
    fig.tight_layout()
    _save(fig, "settlement_benchmarks.pdf")


def figure_concealment() -> None:
    frame = _read("s3_hidden_liquidity.csv")
    if frame.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    _paired_bars(axes[0], frame, "concealed_depth_share",
                 "Concealed share of resting size", "fraction")
    _paired_bars(axes[1], frame, "concealed_size_multiple",
                 "Concealed parent size / plain size", "ratio")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    _save(fig, "concealment.pdf")


def figure_window_profile() -> None:
    frame = _read("s5_window_profile.csv")
    if frame.empty:
        return
    panels = [("spread_bps", "Quoted spread (bps)"),
              ("volume_share", "Share of window volume"),
              ("concealed_share", "Concealed share of resting size"),
              ("cancel_to_entry", "Cancellations per entry")]
    groups = [g for g in GROUP_ORDER if g in set(frame.security_group)]
    fig, axes = plt.subplots(2, 2, figsize=(7.6, 5.0), sharex=True)
    for ax, (column, title) in zip(axes.ravel(), panels):
        if column not in frame.columns:
            ax.set_visible(False)
            continue
        for group, style in zip(groups, ("-", "--", ":")):
            for is_expiry, colour in ((False, CONTROL_COLOUR), (True, EXPIRY_COLOUR)):
                block = frame[(frame.security_group == group)
                              & (frame.is_expiry.astype(bool) == is_expiry)]
                if block.empty:
                    continue
                block = block.sort_values("minute")
                ax.plot(block.minute, pd.to_numeric(block[column], errors="coerce"),
                        style, color=colour, linewidth=1.2,
                        label=f"{_label(group)}, {'expiry' if is_expiry else 'control'}")
        ax.set_title(title, fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("minutes from the window's open")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(3, len(labels)),
               frameon=False, fontsize=7.5, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    _save(fig, "window_profile.pdf")


def figure_forest() -> None:
    frame = _read("hypothesis_testing_summary.csv")
    if frame.empty or "effect_size_cohen_d" not in frame.columns:
        return
    tested = frame[frame.p_value.notna()].copy()
    if tested.empty:
        return
    tested = tested.sort_values("effect_size_cohen_d")

    d = pd.to_numeric(tested.effect_size_cohen_d, errors="coerce").to_numpy(float)
    n = pd.to_numeric(tested.n_pairs, errors="coerce").to_numpy(float)
    # Standard error of Cohen's d for a paired design.
    with np.errstate(divide="ignore", invalid="ignore"):
        error = 1.96 * np.sqrt(1.0 / n + d ** 2 / (2.0 * n))
    supported = tested.get("supported", pd.Series(False, index=tested.index)).to_numpy(bool)
    contradicted = tested.get("contradicted", pd.Series(False, index=tested.index)).to_numpy(bool)

    fig, ax = plt.subplots(figsize=(7.0, 0.22 * len(tested) + 1.2))
    y = np.arange(len(tested))
    ax.errorbar(d, y, xerr=error, fmt="none", ecolor="#bbbbbb", elinewidth=1.1, capsize=2)
    ax.scatter(d[supported], y[supported], s=22, color=EXPIRY_COLOUR,
               label="supported", zorder=3)
    ax.scatter(d[contradicted], y[contradicted], s=26, facecolors="none",
               edgecolors="#b00020", linewidths=1.2, label="contradicted", zorder=3)
    rest = ~(supported | contradicted)
    ax.scatter(d[rest], y[rest], s=16, color="#9a9a9a", label="not rejected", zorder=3)

    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.hypothesis_id}  {str(r.description)[:46]}"
                        for r in tested.itertuples()], fontsize=7)
    ax.set_xlabel("Cohen's $d$ on paired differences (95\\% interval)".replace("\\%", "%"))
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    _save(fig, "effects_forest.pdf")


def build_all_figures() -> None:
    _style()
    for builder in (figure_marking_cost, figure_pressure, figure_settlement,
                    figure_concealment, figure_window_profile, figure_forest):
        try:
            builder()
        except Exception as exc:
            logger.error(f"[FIGURE] {builder.__name__} failed: {exc}")


if __name__ == "__main__":
    build_all_figures()
