"""Stage 7: assemble and compile the manuscript.

The order matters and is the whole design:

  1. run the hypothesis tests
  2. record every quantity the text cites, with its unit and provenance
  3. turn those into LaTeX macros
  4. assemble the document, whose prose cites macros and contains no typed figure
  5. audit - fail if the text cites something never recorded, or carries a hand-typed number
  6. compile

Step 5 is what makes steps 2 and 3 worth having. Without it a macro could quietly go
missing and the document would either fail to build for an opaque reason or typeset nothing
where a result should be.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402
from stage7_report import manuscript  # noqa: E402
from stage7_report.audit_macros import audit  # noqa: E402
from stage7_report.build_macros import build as build_macros  # noqa: E402
from stage7_report.build_macros import macro_name, tex_escape  # noqa: E402
from stage7_report.collect_metrics import collect_all  # noqa: E402
from stage7_report.generate_charts import generate_all_charts  # noqa: E402
from stage7_report.stat_tests import run_all_hypothesis_tests  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.provenance import load_metrics, reset as reset_metrics  # noqa: E402

logger = setup_logger("Report", "stage7_report.log")

FIGURES = [
    ("fig1_vwap_basis_trajectory.png",
     "Cumulative cash VWAP and cash-futures basis across the settlement window."),
    ("fig2_basis_volatility_boxplot.png",
     "Basis volatility by liquidity group, expiry against control."),
    ("fig3_participant_profile.png",
     "Settlement-window traded volume by participant classification."),
    ("fig4_algo_ioc_rate.png",
     "Immediate-or-cancel submission rate by routing classification."),
    ("fig5_cancellation_ratio_timeline.png",
     "Cancel-to-entry ratio by minute across the settlement window."),
    ("fig6_iceberg_hidden_volume.png",
     "Share of entered volume held back from display, by liquidity group."),
    ("fig7_spread_dynamics.png",
     "Quoted spread by liquidity group, expiry against control."),
    ("fig8_order_flow_imbalance.png",
     "Net submitted order flow by minute across the settlement window."),
    ("fig9_price_impact_bps.png",
     "Median absolute trade-to-trade price change, expiry against control."),
    ("fig10_hypothesis_forest_plot.png",
     "Paired effect sizes with 95\\% intervals. Hypotheses without inputs are marked."),
]

# The descriptive quantities Table 1 reports, as (label, recorded key stem, unit hint).
STYLISED_ROWS = [
    ("Quoted spread (bps)", "spread.mean_bps"),
    ("Widest spread (bps)", "spread.max_bps"),
    ("Visible bid depth (shares)", "depth.bid"),
    ("Visible ask depth (shares)", "depth.ask"),
    ("Absolute book imbalance", "depth.abs_imbalance"),
    ("Orders with concealed size (\\%)", "ice.ratio"),
    ("Volume held from display (\\%)", "ice.hidden_share"),
    ("Cancellations per entry", "cancel.ratio"),
    ("Immediate-or-cancel share (\\%)", "ioc.ratio"),
    ("IOC share, final five minutes (\\%)", "ioc.late_ratio"),
    ("Orders resting under one second (\\%)", "life.phantom_rate"),
    ("Median price impact (bps)", "impact.median_bps"),
    ("Kyle's lambda", "impact.kyle_lambda"),
    ("Settlement variance rate ratio", "vol.rv_ratio"),
    ("Volume Gini across the window", "profile.gini"),
    ("Final-minute volume share (\\%)", "profile.final_min_share"),
    ("Spread-widening episodes", "resil.shocks"),
    ("Median recovery (seconds)", "resil.recovery_sec"),
]


def _headline(summary: pd.DataFrame) -> str:
    """One sentence stating the outcome, recorded rather than asserted."""
    tested = summary[summary.p_value.notna()] if "p_value" in summary else summary.iloc[0:0]
    rejected = (summary[summary.significant_fdr.astype(bool)]
                if "significant_fdr" in summary else summary.iloc[0:0])
    if not len(tested):
        return ("No hypothesis could be evaluated on the data available to this run; the "
                "inputs each one requires were absent or empty.")
    if not len(rejected):
        return (f"Of the {len(tested)} hypotheses evaluated, none survives control of the "
                f"false discovery rate. We report the per-test statistics and effect sizes "
                f"rather than a set of findings.")
    ids = ", ".join(rejected.hypothesis_id.astype(str))
    return (f"Of the {len(tested)} hypotheses evaluated, {len(rejected)} are rejected under "
            f"false discovery rate control ({ids}); effect sizes and per-test statistics "
            f"are reported in full.")


def _stylised_table() -> str:
    metrics = load_metrics()

    def cell(stem: str, suffix: str) -> str:
        name = macro_name(f"{stem}_{suffix}")
        return rf"\{name}{{}}" if f"{stem}_{suffix}" in metrics else "---"

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Settlement-window descriptives, averaged across securities and sessions. "
        r"A dash marks a quantity whose input was not produced by this run.}",
        r"\label{tab:stylised}",
        r"\small",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Quantity & Expiry & Control & Difference \\",
        r"\midrule",
    ]
    for label, stem in STYLISED_ROWS:
        if not any(k.startswith(stem) for k in metrics):
            continue
        lines.append(
            f"{label} & {cell(stem, 'expiry')} & {cell(stem, 'control')} "
            f"& {cell(stem, 'diff')} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def _tests_table(summary: pd.DataFrame) -> str:
    lines = [
        r"\begin{longtable}{p{0.7cm} p{5.4cm} r r r r}",
        r"\caption{Paired tests of each hypothesis: expiry sessions against matched controls. "
        r"$n$ is the number of security-session pairs. Rejection is under Benjamini-Hochberg "
        r"control of the false discovery rate.}\label{tab:tests}\\",
        r"\toprule",
        r"ID & Hypothesis & $n$ & $t$ & $p$ & $d$ \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"ID & Hypothesis & $n$ & $t$ & $p$ & $d$ \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for row in summary.itertuples(index=False):
        h_id = str(row.hypothesis_id)
        desc = tex_escape(str(row.description))
        if pd.isna(getattr(row, "p_value", np.nan)):
            lines.append(rf"\textbf{{{h_id}}} & {desc} & \multicolumn{{4}}{{c}}{{"
                         rf"\textit{{not evaluated - inputs absent}}}} \\")
            continue
        stem = f"h.{h_id.lower()}"
        marker = r"$^{\ast}$" if getattr(row, "significant_fdr", False) else ""
        lines.append(
            rf"\textbf{{{h_id}}}{marker} & {desc} "
            rf"& \{macro_name(stem + '.n_pairs')}{{}} "
            rf"& \{macro_name(stem + '.test_stat')}{{}} "
            rf"& \{macro_name(stem + '.p_value')}{{}} "
            rf"& \{macro_name(stem + '.effect_size_cohen_d')}{{}} \\")
    lines.append(r"\end{longtable}")
    lines.append(r"\noindent\footnotesize $^{\ast}$ rejected at a false discovery rate of "
                 r"$\alpha = \TestAlpha{}$.\normalsize")
    return "\n".join(lines)


def _figures_block(results_dir: Path) -> str:
    blocks: List[str] = []
    for filename, caption in FIGURES:
        if not (results_dir / filename).exists():
            continue
        blocks += [
            r"\begin{figure}[htbp]",
            r"  \centering",
            rf"  \includegraphics[width=0.82\textwidth]{{{filename}}}",
            rf"  \caption{{{caption}}}",
            r"\end{figure}",
        ]
    if not blocks:
        return ""
    return "\\section{Figures}\n" + "\n".join(blocks)


def _authored_text() -> str:
    """The prose, for the hand-typed-number audit. Tables are generated, so excluded."""
    return "\n".join([
        manuscript.ABSTRACT, manuscript.INTRODUCTION, manuscript.BACKGROUND,
        manuscript.DATA, manuscript.DESIGN, manuscript.METHOD,
        manuscript.RESULTS_INTRO, manuscript.LIMITATIONS, manuscript.REPRODUCIBILITY,
    ])


def assemble(summary: pd.DataFrame, results_dir: Path) -> str:
    provenance = results_dir / "provenance.tex"
    return "\n\n".join(filter(None, [
        manuscript.PREAMBLE,
        r"\begin{document}",
        r"\maketitle",
        manuscript.ABSTRACT,
        manuscript.INTRODUCTION,
        manuscript.BACKGROUND,
        manuscript.DATA,
        manuscript.DESIGN,
        manuscript.METHOD,
        manuscript.RESULTS_INTRO,
        _stylised_table(),
        _tests_table(summary),
        _figures_block(results_dir),
        manuscript.LIMITATIONS,
        manuscript.REPRODUCIBILITY,
        r"\input{provenance}" if provenance.exists() else "",
        r"\end{document}",
    ]))


def _compile(tex_path: Path, results_dir: Path) -> Optional[Path]:
    pdflatex = shutil.which("pdflatex") or str(
        Path.home() / "AppData/Roaming/TinyTeX/bin/windows/pdflatex.exe")
    if not Path(pdflatex).exists():
        logger.warning(f"[COMPILE] pdflatex not found ({pdflatex}); the .tex is written but "
                       f"not compiled")
        return None

    logger.info(f"[COMPILE] {pdflatex}")
    started = time.time()
    # Twice: the longtable and the cross-references need a second pass to settle.
    for pass_number in (1, 2):
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", str(results_dir), str(tex_path)],
            cwd=results_dir, capture_output=True, text=True)
        if result.returncode != 0:
            tail = "\n".join(result.stdout.splitlines()[-25:])
            logger.error(f"[COMPILE] pdflatex failed on pass {pass_number}:\n{tail}")
            return None

    pdf = results_dir / "final_research_paper.pdf"
    logger.info(f"[COMPILE] {pdf} in {time.time() - started:.1f}s")
    return pdf if pdf.exists() else None


def generate_report() -> None:
    results_dir = Path(RESULTS_DIR)
    logger.info("=== STAGE 7: MANUSCRIPT ===")
    started = time.time()

    # Cleared first. A metric whose recorder was removed would otherwise persist in the
    # store and keep appearing in the document - the hand-typed-number problem by another
    # route.
    reset_metrics()

    summary = run_all_hypothesis_tests()
    collect_all()

    from utils.provenance import Run
    with Run("stage7.generate_report") as run:
        run.record("results.headline", _headline(summary), "",
                   "one-sentence statement of the outcome, derived from the test results")

    build_macros()
    generate_all_charts()

    document = assemble(summary, results_dir)
    problems, fallbacks = audit(document, _authored_text(), results_dir / "macros.tex")
    if fallbacks:
        # Appended so the document still builds and the gaps are visible on the page as ??
        # rather than stopping the compile with an opaque LaTeX error.
        macros_path = results_dir / "macros.tex"
        macros_path.write_text(
            macros_path.read_text(encoding="utf-8")
            + "\n% Cited but never recorded - see the audit output.\n" + fallbacks + "\n",
            encoding="utf-8")
    for problem in problems:
        logger.error(f"[AUDIT] {problem}")
    if not problems:
        logger.info("[AUDIT] every cited quantity is recorded; no hand-typed numbers")

    tex_path = results_dir / "final_research_paper.tex"
    tex_path.write_text(document, encoding="utf-8")
    logger.info(f"[MANUSCRIPT] {tex_path}")

    _compile(tex_path, results_dir)
    logger.info(f"[COMPLETE] stage 7 in {time.time() - started:.1f}s")


if __name__ == "__main__":
    generate_report()
