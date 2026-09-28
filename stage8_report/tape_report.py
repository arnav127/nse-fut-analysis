"""Quantities, tables and figures for the full-year tape and the derivatives analyses.

Kept apart from the paired-test report code because these results have a different shape:
regression coefficients with clustered standard errors and randomization p-values, rather
than one paired test per hypothesis.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PAPER_FIGURES_DIR, PAPER_GENERATED_DIR, RESULTS_DIR  # noqa: E402
from stage8_report.build_macros import macro_name  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.provenance import Run, load_metrics  # noqa: E402

logger = setup_logger("TapeReport", "stage8_report.log")
TABLE_DIR = Path(PAPER_GENERATED_DIR) / "tables"

EVENTS = ["monthly_expiry", "weekly_expiry", "month_end"]
EVENT_LABEL = {"monthly_expiry": "Monthly expiry", "weekly_expiry": "Weekly index expiry",
               "month_end": "Month end", "normal": "Other sessions"}
SAMPLES = ["liquid", "illiquid", "derivative", "placebo", "did"]
SAMPLE_LABEL = {"liquid": "Liquid", "illiquid": "Illiquid", "placebo": "Placebo",
                "derivative": "F\\&O", "did": "F\\&O $-$ placebo"}
PARTS = ["custodian", "proprietary", "ncnp"]
PART_LABEL = {"custodian": "Custodian", "proprietary": "Proprietary", "ncnp": "NCNP"}


def _csv(name: str) -> pd.DataFrame:
    path = Path(RESULTS_DIR) / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _key(*parts: str) -> str:
    return ".".join(p.replace("_", "") if i else p for i, p in enumerate(parts))


# --- recording --------------------------------------------------------------------------

def _record_fit(run: Run, stem: str, row, unit: str, note: str) -> None:
    run.record(stem, float(row.coef), unit, note)
    run.record(f"{stem}.se", float(row.se), unit, f"{note}; standard error clustered by session")
    run.record(f"{stem}.p", float(row.p), "p-value", f"{note}; cluster-robust p-value")
    if "ri_p" in row.index and pd.notna(row.ri_p):
        run.record(f"{stem}.rip", float(row.ri_p), "p-value",
                   f"{note}; randomization p-value over pseudo-expiry sessions")


def collect_tape_metrics() -> None:
    from stage9_tape.settlement_tests import RI_DRAWS

    with Run("stage9.settlement_tests") as run:
        run.record("ri.draws", RI_DRAWS, "draws",
                   "pseudo-expiry samples in each randomization distribution")
        panel_path = Path(RESULTS_DIR) / "s9_panel.parquet"
        if panel_path.exists():
            panel = pd.read_parquet(panel_path, columns=["symbol", "session", "day_type",
                                                         "group"])
            run.record("tape.sessions", int(panel.session.nunique()), "sessions",
                       "trading sessions in the full-year panel")
            run.record("tape.securities", int(panel.symbol.nunique()), "securities",
                       "securities in the full-year panel")
            run.record("tape.observations", int(len(panel)), "observations",
                       "security-sessions in the full-year panel")
            for t, n in panel.drop_duplicates("session").day_type.value_counts().items():
                run.record(f"tape.n.{t.replace('_', '')}", int(n), "sessions",
                           f"sessions of type {t}")

        profile = _csv("s9_day_type_profile.csv")
        for row in profile.itertuples():
            stem = _key("tape.mean", row.group, row.day_type)
            run.record(f"{stem}.share", float(row.window_share), "per cent",
                       "share of session volume traded in the window")
            run.record(f"{stem}.absdrift", float(row.abs_drift), "basis points",
                       "absolute move from the pre-window VWAP to the settlement price")

        event_rows = [(prefix, row)
                      for file_name, prefix in (("s9_activity.csv", "act"),
                                                ("s9_pressure.csv", "press"))
                      for row in _csv(file_name).itertuples(index=False)]
        for prefix, row in event_rows:
            stem = _key(prefix, row.measure, row.sample, row.term)
            unit = ("per cent" if row.measure == "window_share"
                    else "ratio" if "oib" in row.measure else "basis points")
            _record_fit(run, stem, pd.Series(row._asdict()), unit,
                        f"{row.label}, {row.term} against other sessions, {row.sample}")
            if row.sample != "did" and pd.notna(getattr(row, "normal_mean", np.nan)):
                run.record(_key(prefix, row.measure, row.sample, "normal"),
                           float(row.normal_mean), unit, f"{row.label}, other sessions")

        for row in _csv("s9_oib_dynamics.csv").itertuples(index=False):
            stem = _key("oibdyn", row.model, row.sample, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        f"order imbalance {row.model}, {row.term}, {row.sample}")

        for row in _csv("s9_index_channel.csv").itertuples(index=False):
            stem = _key("stockidx", row.group, row.outcome, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "basis points",
                        f"{row.outcome} of the {row.group} group less the placebo group, "
                        f"{row.term}")

        for row in _csv("s10_index_reversal.csv").itertuples(index=False):
            stem = _key("idxrev", row.spec, row.index, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        f"index next-morning return on the window move, {row.term}")
        for row in _csv("s10_index_activity.csv").itertuples(index=False):
            stem = _key("idx", row.index, row.outcome, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "basis points",
                        f"index {row.outcome} on {row.term} sessions against others")
            run.record(_key("idx", row.index, row.outcome, "normal"), float(row.normal_mean),
                       "basis points", f"index {row.outcome}, sessions without expiry")
        for row in _csv("s10_index_pinning.csv").itertuples(index=False):
            stem = _key("idxpin", row.index, row.outcome)
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        f"index distance to a multiple of fifty, {row.outcome}")
            run.record(f"{stem}.normal", float(row.normal_mean), "ratio",
                       "sessions without expiry")
        index_panel = _csv("s10_index_panel.csv")
        if not index_panel.empty:
            days = index_panel.drop_duplicates("session")
            run.record("idx.sessions", int(len(days)), "sessions", "sessions with the index file")
            run.record("idx.expiries", int(days.expiry.sum()), "sessions",
                       "index expiries, weekly and monthly")
            spread = index_panel.pivot(index="session", columns="index", values="drift")
            spread = (spread["nifty"] - spread["next50"]).rename("d").to_frame()
            spread["e"] = days.set_index("session").expiry
            neg = spread.groupby("e").d.apply(lambda v: float((v < 0).mean() * 100))
            run.record("idx.negshare.expiry", neg.get(1.0), "per cent",
                       "share of index expiries on which the Nifty 50 ends the window below "
                       "the Nifty Next 50")
            run.record("idx.negshare.other", neg.get(0.0), "per cent",
                       "the same share on other sessions")

        for row in _csv("s9_reversal.csv").itertuples(index=False):
            stem = _key("rev", row.sample, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        f"next-morning return on the window's move, {row.term}, {row.sample}")

        for row in _csv("s9_flow.csv").itertuples(index=False):
            stem = _key("flow", row.outcome, row.model, row.sample, row.term)
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        f"{row.outcome} on window flow in per cent of median volume")

        slopes = _csv("s7_convergence_slope.csv")
        for row in slopes.itertuples(index=False):
            side = "expiry" if row.is_expiry else "control"
            stem = _key("conv", side, "last5" if row.subset.startswith("final") else "m28")
            _record_fit(run, stem, pd.Series(row._asdict()), "ratio",
                        "slope of the futures price on the cash price, both relative to the "
                        "settlement price")
            run.record(f"{stem}.n", int(row.nobs), "observations", "security-minutes")
            run.record(f"{stem}.fixed", float(100 * row.weight_fixed), "per cent",
                       "median share of window volume already traded")
            run.record(f"{stem}.gapsettle", float(row.gap_settle), "basis points",
                       "median distance of the futures price from the settlement price")
            run.record(f"{stem}.gapcash", float(row.gap_cash), "basis points",
                       "median distance of the futures price from the cash price")
        futures = _csv("s7_futures_summary.csv")
        if not futures.empty:
            run.record("conv.sessions", int(futures.session.nunique()), "sessions",
                       "sessions with the derivatives trade file")
            run.record("conv.securities", int(futures.symbol.nunique()), "securities",
                       "securities with a traded near-month future")
            for flag, block in futures.groupby("is_expiry"):
                side = "expiry" if flag else "control"
                run.record(f"conv.closegap.{side}", float(block.fut_close_gap_bps.median()),
                           "basis points",
                           "median distance of the future's last trade from the settlement "
                           "price")
                run.record(f"conv.windowshare.{side}",
                           float(100 * block.fut_window_share.median()), "per cent",
                           "median share of the future's session volume traded in the window")

        # The order book sample's differences-in-differences, so the text can cite them.
        contrasts = _csv("s6_group_contrasts.csv")
        for row in contrasts.itertuples(index=False):
            column = str(row.source).split(":")[-1].replace("_", "")
            which = "placebo" if str(row.contrast).startswith("settlement") else "liquidity"
            stem = f"did.{column}.{which}"
            run.record(stem, float(row.difference_in_differences), "ratio",
                       f"{row.measure}: {row.contrast}, difference in expiry-minus-control "
                       f"differences")
            run.record(f"{stem}.p", float(row.p_value), "p-value", f"{row.measure}: Welch test")

        pins = _csv("s8_pinning_tests.csv")
        for row in pins.itertuples(index=False):
            stem = _key("pin", row.outcome, row.term)
            unit = "ratio"
            _record_fit(run, stem, pd.Series(row._asdict()), unit,
                        f"strike attraction, {row.outcome}, {row.term}")
            if pd.notna(getattr(row, "control_mean", np.nan)):
                run.record(_key("pin", row.outcome, "controlmean"), float(row.control_mean),
                           unit, f"{row.outcome} on other sessions of the expiry month")
            run.record(_key("pin", row.outcome, row.term, "n"), int(row.nobs), "observations",
                       "security-sessions")
        detail = _csv("s8_strike_pinning.csv")
        if not detail.empty:
            run.record("pin.expiries", int(detail.expiry_session.nunique()), "sessions",
                       "monthly expiries with option strike data")
            run.record("pin.securities", int(detail.symbol.nunique()), "securities",
                       "securities with a stock option strike grid")


# --- tables -----------------------------------------------------------------------------

def _stars(p: float) -> str:
    if not np.isfinite(p):
        return ""
    return "^{***}" if p < 0.01 else "^{**}" if p < 0.05 else "^{*}" if p < 0.1 else ""


def _cell(metrics: Dict, stem: str, digits: int = 2) -> List[str]:
    """Coefficient and standard error as two stacked cells, from the recorded values."""
    if stem not in metrics:
        return ["", ""]
    b = metrics[stem]["value"]
    se = metrics.get(f"{stem}.se", {}).get("value", np.nan)
    p = metrics.get(f"{stem}.p", {}).get("value", np.nan)
    return [f"${b:.{digits}f}{_stars(p)}$", f"$({se:.{digits}f})$"]


def _write(name: str, lines: List[str]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    (TABLE_DIR / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _grid(metrics: Dict, rows: List[tuple], columns: List[str], stem_of) -> List[str]:
    lines = []
    for label, row_key in rows:
        cells = [_cell(metrics, stem_of(row_key, c)) for c in columns]
        if not any(c[0] for c in cells):
            continue
        lines.append(label + " & " + " & ".join(c[0] for c in cells) + r" \\")
        lines.append(" & " + " & ".join(c[1] for c in cells) + r" \\")
    return lines


def table_activity(metrics: Dict) -> None:
    head = " & ".join(SAMPLE_LABEL[s] for s in SAMPLES)
    lines = [r"\begin{tabular}{l" + "c" * len(SAMPLES) + "}", r"\toprule",
             rf" & {head} \\", r"\midrule"]
    measures = [("window_share", "Window share of session volume (pp)"),
                ("abs_drift", r"$|$Settlement price $-$ pre-window VWAP$|$ (bps)"),
                ("abs_terminal", r"$|$Final five minutes $-$ settlement price$|$ (bps)")]
    for measure, title in measures:
        lines.append(rf"\multicolumn{{{len(SAMPLES) + 1}}}{{l}}{{\textit{{{title}}}}} \\")
        base = []
        for s in SAMPLES:
            k = _key("act", measure, s, "normal")
            base.append(f"{metrics[k]['value']:.2f}" if k in metrics else "")
        lines.append(r"\quad Other sessions (mean) & " + " & ".join(base) + r" \\")
        lines += _grid(metrics, [(rf"\quad {EVENT_LABEL[t]}", t) for t in EVENTS], SAMPLES,
                       lambda t, s, m=measure: _key("act", m, s, t))
        lines.append(r"\addlinespace[3pt]")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("activity", lines)


def table_reversal(metrics: Dict) -> None:
    head = " & ".join(SAMPLE_LABEL[s] for s in SAMPLES)
    lines = [r"\begin{tabular}{l" + "c" * len(SAMPLES) + "}", r"\toprule",
             rf" & {head} \\", r"\midrule"]
    rows = [("Window move", "drift")] + [(rf"Window move $\times$ {EVENT_LABEL[t].lower()}",
                                          f"drift_x_{t}") for t in EVENTS]
    lines += _grid(metrics, rows, SAMPLES, lambda r, s: _key("rev", s, r))
    ri = []
    for s in SAMPLES:
        k = _key("rev", s, "drift_x_monthly_expiry") + ".rip"
        ri.append(f"{metrics[k]['value']:.3f}" if k in metrics else "")
    lines += [r"\midrule", r"Randomization $p$, monthly expiry & " + " & ".join(ri) + r" \\"]
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("reversal", lines)


def table_flow(metrics: Dict) -> None:
    columns = [("drift", "derivative"), ("next_rev", "derivative"),
               ("drift", "placebo"), ("next_rev", "placebo")]
    lines = [r"\begin{tabular}{lcccc}", r"\toprule",
             r" & \multicolumn{2}{c}{F\&O securities} & \multicolumn{2}{c}{Placebo} \\",
             r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
             r" & Window move & Next morning & Window move & Next morning \\", r"\midrule"]
    rows = [("Net aggressor flow", "flow"),
            (r"Net aggressor flow $\times$ monthly expiry", "flow_x_monthly_expiry")]
    lines.append(r"\multicolumn{5}{l}{\textit{All participants}} \\")
    lines += _grid(metrics, [(rf"\quad {a}", b) for a, b in rows], columns,
                   lambda r, c: _key("flow", c[0], "all", c[1], r))
    lines.append(r"\addlinespace[3pt]")
    lines.append(r"\multicolumn{5}{l}{\textit{By aggressor category}} \\")
    part_rows = []
    for p in PARTS:
        part_rows.append((rf"\quad {PART_LABEL[p]}", f"flow_{p}"))
        part_rows.append((rf"\quad {PART_LABEL[p]} $\times$ monthly expiry",
                          f"flow_{p}_x_monthly_expiry"))
    lines += _grid(metrics, part_rows, columns,
                   lambda r, c: _key("flow", c[0], "participant", c[1], r))
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("flow", lines)


def table_derivatives(metrics: Dict) -> None:
    lines = [r"\begin{tabular}{lcc}", r"\toprule",
             r" & Expiry sessions & Control sessions \\", r"\midrule",
             r"\multicolumn{3}{l}{\textit{Slope of the futures price on the cash price}} \\"]
    lines += _grid(metrics, [(r"\quad Final five minutes", "last5"),
                             (r"\quad Minute beginning 15:28", "m28")],
                   ["expiry", "control"], lambda r, c: _key("conv", c, r))
    lines.append(r"\addlinespace[3pt]")
    for label, suffix in (("Window volume already traded at 15:28 (\\%)", "fixed"),
                          ("Futures vs settlement price at 15:28 (median bps)", "gapsettle"),
                          ("Futures vs cash price at 15:28 (median bps)", "gapcash")):
        cells = []
        for side in ("expiry", "control"):
            k = _key("conv", side, "m28") + "." + suffix
            cells.append(f"{metrics[k]['value']:.1f}" if k in metrics else "")
        lines.append(label + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("convergence", lines)

    lines = [r"\begin{tabular}{lccc}", r"\toprule",
             r" & Distance to strike & Within a tenth of an interval & Change in the window \\",
             r"\midrule"]
    base = []
    for y in ("distance", "near", "change"):
        k = _key("pin", y, "controlmean")
        base.append(f"{metrics[k]['value']:.3f}" if k in metrics else "")
    lines.append(r"Other sessions of the month (mean) & " + " & ".join(base) + r" \\")
    for label, term in (("Expiry session", "expiry"),
                        (r"Expiry $\times$ high option activity", "expiry_x_high")):
        cells = [_cell(metrics, _key("pin", y, term), 3) for y in ("distance", "near", "change")]
        lines.append(label + " & " + " & ".join(c[0] for c in cells) + r" \\")
        lines.append(" & " + " & ".join(c[1] for c in cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("pinning", lines)


def table_pressure(metrics: Dict) -> None:
    head = " & ".join(SAMPLE_LABEL[x] for x in SAMPLES)
    lines = [r"\begin{tabular}{l" + "c" * len(SAMPLES) + "}", r"\toprule",
             rf" & {head} \\", r"\midrule"]
    blocks = [("abs_oib", "$|$Order imbalance$|$ over the window", 3),
              ("oib", "Order imbalance over the window", 3),
              ("abs_move1530", r"$|$Move from 15:00 to 15:30$|$ (bps)", 2)]
    for measure, title, digits in blocks:
        lines.append(rf"\multicolumn{{{len(SAMPLES) + 1}}}{{l}}{{\textit{{{title}}}}} \\")
        base = []
        for x in SAMPLES:
            k = _key("press", measure, x, "normal")
            base.append(f"{metrics[k]['value']:.{digits}f}" if k in metrics else "")
        lines.append(r"\quad Other sessions (mean) & " + " & ".join(base) + r" \\")
        for t in ("monthly_expiry", "weekly_expiry"):
            cells = [_cell(metrics, _key("press", measure, x, t), digits) for x in SAMPLES]
            lines.append(rf"\quad {EVENT_LABEL[t]} & " + " & ".join(c[0] for c in cells)
                         + r" \\")
            lines.append(" & " + " & ".join(c[1] for c in cells) + r" \\")
        lines.append(r"\addlinespace[3pt]")
    lines.append(rf"\multicolumn{{{len(SAMPLES) + 1}}}{{l}}{{\textit{{Persistence of order "
                 r"imbalance from one five-minute block to the next}} \\")
    for label, term in (("Other sessions", "lag"), ("Monthly expiry", "lag_x_monthly_expiry"),
                        ("Weekly index expiry", "lag_x_weekly_expiry")):
        cells = [_cell(metrics, _key("oibdyn", "persistence", x, term), 3) for x in SAMPLES]
        lines.append(rf"\quad {label} & " + " & ".join(c[0] for c in cells) + r" \\")
        lines.append(" & " + " & ".join(c[1] for c in cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("pressure", lines)


def table_index(metrics: Dict) -> None:
    cols = [("nifty", "Nifty 50"), ("next50", "Nifty Next 50"), ("spread", "Difference")]
    lines = [r"\begin{tabular}{lccc}", r"\toprule",
             " & " + " & ".join(c[1] for c in cols) + r" \\", r"\midrule"]
    rows = [("drift", "Move from pre-window to settlement value (bps)"),
            ("move", "Move from 15:00 to 15:30 (bps)"),
            ("next_rev", "Next-morning return from the settlement value (bps)"),
            ("abs_drift", r"$|$Move from pre-window to settlement value$|$ (bps)")]
    for outcome, title in rows:
        lines.append(rf"\multicolumn{{4}}{{l}}{{\textit{{{title}}}}} \\")
        base = []
        for c, _ in cols:
            k = _key("idx", c, outcome, "normal")
            base.append(f"{metrics[k]['value']:.2f}" if k in metrics else "")
        lines.append(r"\quad Sessions without expiry (mean) & " + " & ".join(base) + r" \\")
        for label, term in (("Index expiry", "expiry"), ("Monthly expiry, additional", "monthly")):
            cells = [_cell(metrics, _key("idx", c, outcome, term)) for c, _ in cols]
            lines.append(rf"\quad {label} & " + " & ".join(x[0] for x in cells) + r" \\")
            lines.append(" & " + " & ".join(x[1] for x in cells) + r" \\")
        ri = []
        for c, _ in cols:
            k = _key("idx", c, outcome, "expiry") + ".rip"
            ri.append(f"{metrics[k]['value']:.3f}" if k in metrics else "")
        lines.append(r"\quad Randomization $p$, index expiry & " + " & ".join(ri) + r" \\")
        lines.append(r"\addlinespace[3pt]")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("index", lines)


def build_tape_tables() -> None:
    metrics = load_metrics()
    for builder in (table_activity, table_reversal, table_flow, table_derivatives,
                    table_pressure, table_index):
        try:
            builder(metrics)
        except Exception as exc:
            logger.error(f"[TABLES] {builder.__name__} failed: {exc}")


# --- figures ----------------------------------------------------------------------------

def _save(fig, name: str) -> None:
    import matplotlib.pyplot as plt

    Path(PAPER_FIGURES_DIR).mkdir(parents=True, exist_ok=True)
    fig.savefig(Path(PAPER_FIGURES_DIR) / name)
    plt.close(fig)


COLOURS = {"monthly_expiry": "#1f4e79", "weekly_expiry": "#c55a11", "month_end": "#548235",
           "normal": "#9a9a9a"}


def figure_window_path() -> None:
    import matplotlib.pyplot as plt

    frame = _csv("s9_window_path.csv")
    if frame.empty:
        return
    order = ["pre", "w1", "w2", "w3", "w4", "w5", "w6", "next_open"]
    ticks = ["14:50", "15:05", "15:10", "15:15", "15:20", "15:25", "15:30", "next\nopen"]
    groups = [("liquid", "Liquid F&O"), ("illiquid", "Illiquid F&O"), ("placebo", "Placebo")]
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 2.8), sharey=True)
    for ax, (group, title) in zip(axes, groups):
        for kind in ("normal", "weekly_expiry", "month_end", "monthly_expiry"):
            block = frame[(frame.group == group) & (frame.day_type == kind)]
            block = block.set_index("point").reindex(order)
            if block["mean"].isna().all():
                continue
            ax.plot(range(len(order)), block["mean"], marker="o", markersize=2.5,
                    linewidth=1.8 if kind == "monthly_expiry" else 1.0,
                    color=COLOURS[kind], label=EVENT_LABEL[kind])
        ax.axhline(0, color="#333333", linewidth=0.6)
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(ticks, fontsize=6.5)
        ax.set_title(title, fontsize=9)
    axes[0].set_ylabel("bps, in the direction of the window's move")
    axes[0].legend(frameon=False, fontsize=6.5, loc="upper left")
    fig.tight_layout()
    _save(fig, "window_path.pdf")


def figure_day_types() -> None:
    import matplotlib.pyplot as plt

    frame = _csv("s9_day_type_profile.csv")
    if frame.empty:
        return
    kinds = ["normal", "month_end", "weekly_expiry", "monthly_expiry"]
    groups = ["liquid", "illiquid", "placebo"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.8))
    width = 0.2
    for ax, column, title in ((axes[0], "window_share", "Window share of session volume (%)"),
                              (axes[1], "abs_drift", "|Settlement price - pre-window| (bps)")):
        for i, kind in enumerate(kinds):
            heights = [frame[(frame.group == g) & (frame.day_type == kind)][column].mean()
                       for g in groups]
            ax.bar(np.arange(len(groups)) + (i - 1.5) * width, heights, width,
                   color=COLOURS[kind], label=EVENT_LABEL[kind])
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(["Liquid F&O", "Illiquid F&O", "Placebo"])
        ax.set_title(title, fontsize=9)
    axes[0].legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    _save(fig, "day_types.pdf")


def figure_convergence() -> None:
    import matplotlib.pyplot as plt

    frame = _csv("s7_futures_convergence.csv")
    if frame.empty:
        return
    frame["abs_spot"] = frame.basis_spot.abs()
    frame["abs_proj"] = frame.basis_settle.abs()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7), sharey=True)
    for ax, flag, title in ((axes[0], True, "Expiry sessions"),
                            (axes[1], False, "Control sessions")):
        block = frame[frame.is_expiry == flag].groupby("minute")[["abs_spot", "abs_proj"]]
        med = block.median()
        ax.plot(med.index, med.abs_spot, color="#9a9a9a", label="against the cash price")
        ax.plot(med.index, med.abs_proj, color="#1f4e79",
                label="against the settlement price")
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("minutes from 15:00")
    axes[0].set_ylabel("median |futures - benchmark| (bps)")
    axes[0].legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save(fig, "convergence.pdf")


def figure_pinning() -> None:
    import matplotlib.pyplot as plt

    frame = _csv("s8_strike_pinning.csv")
    if frame.empty:
        return
    bins = np.linspace(0, 0.5, 11)
    fig, ax = plt.subplots(figsize=(4.2, 2.7))
    for flag, colour, label in ((False, "#9a9a9a", "Other sessions of the month"),
                                (True, "#1f4e79", "Expiry session")):
        values = frame[frame.is_expiry == flag].distance.dropna()
        ax.hist(values, bins=bins, density=True, histtype="step" if not flag else "stepfilled",
                alpha=0.55 if flag else 1.0, color=colour, linewidth=1.4, label=label)
    ax.axhline(2.0, color="#333333", linewidth=0.7, linestyle="--")
    ax.set_xlabel("distance of the settlement price to the nearest strike (intervals)")
    ax.set_ylabel("density")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save(fig, "pinning.pdf")


def figure_index_path() -> None:
    import matplotlib.pyplot as plt

    frame = _csv("s10_index_panel.csv")
    if frame.empty:
        return
    wide = {}
    points = ["pre10", "w1", "w2", "w3", "w4", "w5", "w6", "next_open30"]
    for col in points:
        w = frame.pivot(index="session", columns="index", values=col)
        wide[col] = w
    ref = wide["pre10"]
    rel = {c: 1e4 * (np.log(wide[c]["nifty"] / ref["nifty"])
                     - np.log(wide[c]["next50"] / ref["next50"])) for c in points}
    rel = pd.DataFrame(rel)
    kinds = frame.drop_duplicates("session").set_index("session").day_type
    rel["kind"] = kinds.reindex(rel.index).map(
        lambda k: "Index expiry" if k in ("monthly_expiry", "weekly_expiry") else "Other")
    ticks = ["14:50", "15:05", "15:10", "15:15", "15:20", "15:25", "15:30", "next\nopen"]
    fig, ax = plt.subplots(figsize=(5.2, 2.9))
    for kind, colour in (("Other", "#9a9a9a"), ("Index expiry", "#1f4e79")):
        block = rel[rel.kind == kind][points]
        mean, sem = block.mean(), block.sem()
        x = np.arange(len(points))
        ax.plot(x, mean, marker="o", markersize=3, color=colour, label=kind)
        ax.fill_between(x, mean - 1.96 * sem, mean + 1.96 * sem, color=colour, alpha=0.15)
    ax.axhline(0, color="#333333", linewidth=0.6)
    ax.set_xticks(range(len(points)))
    ax.set_xticklabels(ticks, fontsize=7)
    ax.set_ylabel("Nifty 50 less Nifty Next 50 (bps)")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save(fig, "index_path.pdf")


def build_tape_figures() -> None:
    for builder in (figure_window_path, figure_day_types, figure_convergence, figure_pinning,
                    figure_index_path):
        try:
            builder()
        except Exception as exc:
            logger.error(f"[FIGURE] {builder.__name__} failed: {exc}")
