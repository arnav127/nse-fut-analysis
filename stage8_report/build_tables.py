"""Generate the report's tables as LaTeX fragments the manuscript inputs.

Tables are generated rather than authored because their contents change with the data, but
their *structure* is fixed here rather than in the prose, so the manuscript stays readable:
`\\input{generated/tables/tests}` in the results section, and the row-by-row detail out of
the way.

Values come through macros wherever a single number is involved, so a table cell and a
sentence quoting the same quantity cannot disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PAPER_GENERATED_DIR, RESULTS_DIR  # noqa: E402
from config.universe import GROUPS, META, is_derived_universe  # noqa: E402
from stage8_report.build_macros import macro_name, tex_escape  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.provenance import load_metrics  # noqa: E402

logger = setup_logger("Tables", "stage8_report.log")
TABLE_DIR = Path(PAPER_GENERATED_DIR) / "tables"

# (label, recorded key stem) for the descriptive table. Rows whose stem was never recorded
# are dropped rather than printed with dashes, so the table describes this run.
DESCRIPTIVE_ROWS = [
    ("Quoted spread (bps)", "spread.mean_bps"),
    ("Displayed depth, top ten levels", "depth.bid"),
    ("Displayed notional in the book (cr)", "book.visible_cr"),
    ("Price move per probe sweep (bps)", "move.bps_small"),
    ("Median price impact (bps)", "impact.median_bps"),
    ("Impact of one-sided flow at 10s (bps)", "impact.short_bps"),
    ("Permanent share of that impact", "impact.permanent_share"),
    ("Variance ratio", "variance.ratio"),
    ("Signed flow persistence", "flow.persistence"),
    ("$|$Settlement VWAP $-$ open mid$|$ (bps)", "abs.drift_bps"),
    ("$|$Settlement VWAP $-$ close$|$ (bps)", "abs.reversal_bps"),
    ("$|$Final minute $-$ window VWAP$|$ (bps)", "terminal.gap_bps"),
    ("Volume at the running VWAP (\\%)", "vwap.tracking_share"),
    ("Final-minute volume share (\\%)", "final.minute_share"),
    ("Concealed share of resting size (\\%)", "concealed.depth_share"),
    ("Concealed parent size multiple", "concealed.size_multiple"),
    ("Replenishments per 1000 matched", "concealed.replenishment_rate"),
    ("Cancellations per entry", "cancel.ratio"),
    ("Cancelled within one second (\\%)", "life.phantom_rate"),
    ("Realised variance rate ratio", "vol.rv_ratio"),
]


def _write(name: str, lines: List[str]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    (TABLE_DIR / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cite(stem: str, suffix: str, metrics: dict) -> str:
    key = f"{stem}_{suffix}"
    return rf"\{macro_name(key)}{{}}" if key in metrics else "---"


def build_universe_table() -> None:
    lines = [
        r"\begin{table}[H]", r"\centering",
        r"\caption{The securities studied. Liquid and illiquid groups are both derivatives "
        r"underlyings and face the same settlement incentive; the placebo group has no "
        r"expiring contract.}",
        r"\label{tab:universe}", r"\small",
        r"\begin{tabular}{llrp{6.6cm}}", r"\toprule",
        r"Group & Derivatives & $n$ & Members \\", r"\midrule",
    ]
    for group in GROUPS.values():
        if not group.symbols:
            lines.append(rf"{tex_escape(group.label)} & "
                         rf"{'yes' if group.derivatives_eligible else 'no'} & 0 & "
                         rf"\textit{{empty in this run}} \\")
            continue
        shown = ", ".join(tex_escape(s) for s in group.symbols[:10])
        if len(group.symbols) > 10:
            shown += rf", \dots\ ({len(group.symbols) - 10} more)"
        lines.append(rf"{tex_escape(group.label)} & "
                     rf"{'yes' if group.derivatives_eligible else 'no'} & "
                     rf"{len(group.symbols)} & \small {shown} \\")
        lines.append(r"\addlinespace[2pt]")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _write("universe", lines)


def build_selection_table() -> None:
    """The filter cascade, so the reader can see what each criterion removed.

    Reporting only the securities that survived leaves the criteria unfalsifiable: a filter
    whose effect is not shown is a researcher degree of freedom the reader cannot audit.
    """
    filters = META.get("filters") or {}
    if not filters:
        _write("selection", [
            r"\textit{The universe for this run was not derived from the tape, so there is "
            r"no selection cascade to report. See Section~\ref{sec:limitations}.}"])
        return

    steps = [
        ("Traded in the parsed sessions", "symbols_traded",
         "every equity-series security with at least one trade"),
        ("Present in every session", "after_present_in_all_sessions",
         "a security absent for a month cannot contribute that month's matched pair"),
        ("Above the activity floor", "after_activity_floor",
         "below it a one-second snapshot sees nothing happen between observations"),
        ("Stable turnover rank", "after_rank_stability",
         "a security that moves between groups during the year belongs to neither"),
    ]
    lines = [
        r"\begin{table}[H]", r"\centering",
        r"\caption{Selection cascade. Each row reports the securities remaining after the "
        r"criterion in that row is applied, and why the criterion exists.}",
        r"\label{tab:selection}", r"\small",
        r"\begin{tabular}{lrp{7.4cm}}", r"\toprule",
        r"Criterion & Remaining & Reason \\", r"\midrule",
    ]
    previous = None
    for label, key, reason in steps:
        value = filters.get(key)
        if value is None:
            continue
        removed = "" if previous is None else rf" \small($-${previous - value:,})\normalsize"
        lines.append(rf"{label} & {value:,}{removed} & \small {reason} \\")
        previous = value
    size = META.get("group_size")
    if size:
        lines.append(r"\midrule")
        lines.append(rf"Selected & {3 * size:,} & \small {size} most traded and {size} least "
                     rf"traded derivatives underlyings, plus {size} matched securities with "
                     rf"no derivative \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _write("selection", lines)


def build_balance_table() -> None:
    """How alike the groups are on what the matching was meant to equalise.

    Standard for a matched design, and load-bearing here: the placebo group is useful only if
    it resembles the group it stands in for, and a reader cannot take that on trust.
    """
    balance = META.get("balance") or []
    if not balance:
        _write("balance", [
            r"\textit{The universe for this run was not built from the tape, so no balance "
            r"statistics are available and the groups are the development list rather than "
            r"the study universe. See Section~\ref{sec:limitations}.}"])
        return

    overlap = META.get("placebo_adv_overlap") or {}
    lines = [
        r"\begin{table}[H]", r"\centering",
        r"\caption{Group balance on the variables the placebo group is matched on. Turnover "
        r"is measured on control sessions only, so group membership does not depend on "
        r"expiry-day behaviour. Parenthesised ranges are the group minimum and maximum.}",
        r"\label{tab:balance}", r"\small",
        r"\begin{tabular}{lrrrr}", r"\toprule",
        r"Group & $n$ & Turnover (cr/day) & Price (Rs) & Trades/session \\",
        r"\midrule",
    ]
    for row in balance:
        lines.append(
            f"{tex_escape(str(row['group']))} & {row['n']} & "
            f"{row['adv_cr_median']:,.1f} "
            f"({row['adv_cr_min']:,.1f}--{row['adv_cr_max']:,.1f}) & "
            f"{row['price_median']:,.0f} & {row['trades_per_session_median']:,.0f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    if overlap:
        # Which comparison the placebo actually licenses. A security traded as heavily as the
        # liquid group and carrying no derivative barely exists - close to the reason the
        # liquid group has derivatives - so the placebo can only stand in for the illiquid
        # group, and the report should not imply otherwise.
        # The percent sign is escaped: a bare % starts a LaTeX comment and silently drops the
        # rest of the sentence from the document.
        parts = ", ".join(f"{share * 100:.0f}\\% of the {tex_escape(name)} group"
                          for name, share in overlap.items())
        lines.append(
            r"\vspace{0.4em}\par\noindent\footnotesize The placebo group's turnover range "
            rf"covers {parts}. The placebo comparison therefore speaks to the group whose "
            r"range it overlaps and not to the other: a security traded as heavily as the "
            r"liquid group and carrying no derivative is close to a contradiction in terms."
            r"\normalsize")
    lines.append(r"\end{table}")
    _write("balance", lines)


def build_descriptives_table() -> None:
    metrics = load_metrics()
    lines = [
        r"\begin{table}[H]", r"\centering",
        r"\caption{Settlement-window descriptives, averaged over securities and sessions.}",
        r"\label{tab:descriptives}", r"\small",
        r"\begin{tabular}{lrrr}", r"\toprule",
        r"Quantity & Expiry & Control & Difference \\", r"\midrule",
    ]
    for label, stem in DESCRIPTIVE_ROWS:
        if f"{stem}_expiry" not in metrics:
            continue
        lines.append(f"{label} & {_cite(stem, 'expiry', metrics)} & "
                     f"{_cite(stem, 'control', metrics)} & {_cite(stem, 'diff', metrics)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _write("descriptives", lines)


BROAD_TITLES = {
    "BH1": "BH1: The settlement price behaves differently on expiry days",
    "BH2": "BH2: Trading in the window is more costly",
    "BH3": "BH3: Trading in the window is more one-sided",
    "BH4": "BH4: Order behaviour and participation change",
}


def _p_text(p: float) -> str:
    if not np.isfinite(p):
        return "--"
    if p < 0.001:
        return "$<0.001$"
    return f"{p:.3f}"


def build_primary_table() -> None:
    """The four primary tests, with the placebo contrast for each."""
    path = Path(RESULTS_DIR) / "hypothesis_testing_summary.csv"
    if not path.exists():
        return
    summary = pd.read_csv(path)
    if "primary" not in summary.columns:
        return
    contrasts = pd.read_csv(Path(RESULTS_DIR) / "s6_group_contrasts.csv") \
        if (Path(RESULTS_DIR) / "s6_group_contrasts.csv").exists() else pd.DataFrame()
    labels = {"S1": "|Settlement VWAP - open mid| (bps)", "H12": "Quoted spread (bps)",
              "OIB": "|Order imbalance|", "H28": "Orders cancelled within one second"}
    measures = {"S1": r"$|$Settlement VWAP $-$ mid at 15:00$|$ (bps)",
                "H12": "Quoted spread (bps)", "OIB": r"$|$Order imbalance$|$",
                "H28": r"Orders cancelled within one second (\%)"}
    scale = {"H28": 100.0}
    lines = [r"\begin{tabular}{llrrrrrc}", r"\toprule",
             r" & Primary measure & Expiry & Control & $d$ & $p$ & $p \times 4$ & Placebo $p$ \\",
             r"\midrule"]
    prim = summary[summary.primary.astype(bool)].copy()
    prim["order"] = prim.broad.map({"BH1": 1, "BH2": 2, "BH3": 3, "BH4": 4})
    for row in prim.sort_values("order").itertuples(index=False):
        k = scale.get(row.hypothesis_id, 1.0)
        placebo = np.nan
        if not contrasts.empty:
            hit = contrasts[(contrasts.measure == labels.get(row.hypothesis_id))
                            & (contrasts.contrast == "settlement vs calendar")]
            if len(hit):
                placebo = float(hit.p_value.iloc[0])
        mark = r"$^{\ast}$" if bool(row.primary_fdr) else ""
        lines.append(
            f"{row.broad}{mark} & {measures.get(row.hypothesis_id, row.description)} & "
            f"{row.mean_expiry * k:.3f} & {row.mean_control * k:.3f} & "
            f"{row.effect_size_cohen_d:.3f} & {_p_text(row.p_value)} & "
            f"{_p_text(getattr(row, 'bonferroni_primary', np.nan))} & {_p_text(placebo)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    _write("primary", lines)


def build_tests_table() -> None:
    """Every measure, grouped under its broad hypothesis: the appendix."""
    path = Path(RESULTS_DIR) / "hypothesis_testing_summary.csv"
    if not path.exists():
        _write("tests", [r"\textit{No test results were produced by this run.}"])
        return
    summary = pd.read_csv(path)
    if "broad" not in summary.columns:
        summary["broad"] = ""
        summary["subgroup"] = ""
        summary["primary"] = False
    lines = [
        r"\begin{longtable}{p{0.9cm} p{7.4cm} r r r r}",
        r"\caption{Every measure, grouped under the broad hypothesis it belongs to. Each is a "
        r"paired test of the expiry session against the control session of the same month, "
        r"one pair per security. $n$ is the number of pairs and $d$ Cohen's $d$. The primary "
        r"measure of each broad hypothesis is marked P.}\label{tab:tests}\\",
        r"\toprule", r"ID & Measure & $n$ & $t$ & $p$ & $d$ \\", r"\midrule", r"\endfirsthead",
        r"\toprule", r"ID & Measure & $n$ & $t$ & $p$ & $d$ \\", r"\midrule", r"\endhead",
        r"\bottomrule", r"\endfoot", r"\bottomrule", r"\endlastfoot",
    ]
    for broad in ("BH1", "BH2", "BH3", "BH4"):
        block = summary[summary.broad == broad]
        if block.empty:
            continue
        lines.append(rf"\multicolumn{{6}}{{l}}{{\textbf{{{tex_escape(BROAD_TITLES[broad])}}}}} \\")
        block = block.assign(rank=~block.primary.astype(bool))
        for sub, part in block.groupby(block.subgroup.fillna(""), sort=False):
            if sub:
                lines.append(rf"\multicolumn{{6}}{{l}}{{\quad\textit{{{tex_escape(sub)}}}}} \\")
            for row in part.sort_values(["rank", "hypothesis_id"]).itertuples(index=False):
                hid = str(row.hypothesis_id)
                tag = rf"{hid}\,P" if bool(row.primary) else hid
                desc = tex_escape(str(row.description))
                if pd.isna(row.p_value):
                    lines.append(rf"{tag} & {desc} & \multicolumn{{4}}{{c}}{{\textit{{not evaluated}}}} \\")
                    continue
                lines.append(f"{tag} & {desc} & {int(row.n_pairs):,} & {row.test_stat:.2f} & "
                             f"{_p_text(row.p_value)} & {row.effect_size_cohen_d:.3f} \\\\")
        lines.append(r"\addlinespace[4pt]")
    lines.append(r"\end{longtable}")
    _write("tests", lines)


def build_contrasts_table() -> None:
    path = Path(RESULTS_DIR) / "s6_group_contrasts.csv"
    if not path.exists():
        _write("contrasts", [r"\textit{The group contrasts were not produced by this run.}"])
        return
    frame = pd.read_csv(path)
    if frame.empty:
        _write("contrasts", [r"\textit{No group contrasts could be computed.}"])
        return

    lines = [
        r"\begin{table}[H]", r"\centering",
        r"\caption{Differences-in-differences on per-security expiry-minus-control "
        r"differences. The first contrast asks whether an effect belongs to the settlement "
        r"or to the calendar; the second whether it is larger where moving the price is "
        r"cheaper.}",
        r"\label{tab:contrasts}", r"\footnotesize",
        r"\begin{tabular}{lrrrr}", r"\toprule",
        r"Measure & Treated & Reference & Difference & $p$ \\", r"\midrule",
    ]
    for contrast, block in frame.groupby("contrast", sort=False):
        label = {"settlement vs calendar": "Securities with derivatives against the placebo group",
                 "illiquid vs liquid": "Illiquid against liquid"}.get(str(contrast), str(contrast))
        lines.append(rf"\multicolumn{{5}}{{l}}{{\textit{{{tex_escape(label)}}}}} \\")
        for row in block.itertuples(index=False):
            stars = "*" if row.p_value < 0.05 else ""
            lines.append(
                f"\\quad {tex_escape(str(row.measure))} & {row.treated_mean:,.3f} & "
                f"{row.reference_mean:,.3f} & {row.difference_in_differences:,.3f} & "
                f"{row.p_value:.3f}{stars} \\\\")
        lines.append(r"\addlinespace[3pt]")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _write("contrasts", lines)


def build_out_of_scope_table() -> None:
    try:
        from stage8_report.stat_tests import OUT_OF_SCOPE
    except ImportError:
        OUT_OF_SCOPE = []
    if not OUT_OF_SCOPE:
        _write("out_of_scope", [r"\textit{None.}"])
        return
    lines = [r"\begin{table}[H]", r"\centering", r"\small",
             r"\caption{Specified but not evaluable on the data held.}",
             r"\label{tab:outofscope}",
             r"\begin{tabular}{lp{5.6cm}p{5.2cm}}", r"\toprule",
             r"ID & Hypothesis & Why not \\", r"\midrule"]
    for hid, description, reason in OUT_OF_SCOPE:
        lines.append(rf"\textbf{{{hid}}} & {tex_escape(description)} & "
                     rf"{tex_escape(reason)} \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _write("out_of_scope", lines)


def build_all_tables() -> None:
    build_universe_table()
    build_selection_table()
    build_balance_table()
    build_descriptives_table()
    build_tests_table()
    build_primary_table()
    build_contrasts_table()
    build_out_of_scope_table()
    logger.info(f"[TABLES] written to {TABLE_DIR}")


if __name__ == "__main__":
    build_all_tables()
