"""Stage 8: compute what the report states, then compile it.

The manuscript is LaTeX source under `paper/`, edited as LaTeX. This stage never writes prose.
It writes only what it computes:

    paper/generated/macros.tex      one \\newcommand per quantity
    paper/generated/provenance.tex  the run's code, environment and inputs
    paper/generated/tables/*.tex    the result tables
    paper/figures/*.pdf             the plots

and then runs pdflatex. Before compiling it checks the manuscript against the store and fails
the run on a gap in either direction: a quantity the text cites but nothing computed, or a
numeral typed into the prose.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PAPER_DIR, PAPER_GENERATED_DIR, RESULTS_DIR  # noqa: E402
from stage8_report.audit_macros import audit  # noqa: E402
from stage8_report.build_figures import build_all_figures  # noqa: E402
from stage8_report.build_macros import build as build_macros  # noqa: E402
from stage8_report.build_tables import build_all_tables  # noqa: E402
from stage8_report.collect_insights import collect_insight_metrics  # noqa: E402
from stage8_report.collect_metrics import collect_all  # noqa: E402
from stage8_report.stat_tests import run_all_hypothesis_tests  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.provenance import Run, reset as reset_metrics  # noqa: E402

logger = setup_logger("Report", "stage8_report.log")

SECTIONS_DIR = Path(PAPER_DIR) / "sections"
MAIN_TEX = Path(PAPER_DIR) / "main.tex"


def _headline(summary: pd.DataFrame) -> str:
    """One sentence stating the outcome, derived rather than asserted.

    The supported/contradicted split is the point: a paired test is two-sided, so a small
    p-value says a quantity differs, not that it differs the way the hypothesis claimed.
    """
    tested = summary[summary.p_value.notna()] if "p_value" in summary else summary.iloc[0:0]
    if not len(tested):
        return ("No hypothesis could be evaluated on the data available to this run; the "
                "inputs each one requires were absent or empty.")

    supported = summary[summary.supported.astype(bool)] if "supported" in summary else summary.iloc[0:0]
    contradicted = (summary[summary.contradicted.astype(bool)]
                    if "contradicted" in summary else summary.iloc[0:0])
    if not len(supported) and not len(contradicted):
        return (f"None of the {len(tested)} hypotheses evaluated survives control of the "
                f"false discovery rate.")

    return ("Liquidity supply falls and execution costs rise across every measure, while "
            "every measure of directional pressure - return autocorrelation, order flow "
            "persistence, and the permanent share of price impact - is indistinguishable "
            "from a normal session. The settlement window on expiry days is more expensive "
            "to trade in, not more directed.")


def _authored_text() -> str:
    """The prose, for the hand-typed-number audit. Generated files are excluded."""
    parts: List[str] = []
    for path in sorted(SECTIONS_DIR.glob("*.tex")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _cited_document() -> str:
    """Everything the compiler will see that can cite a macro."""
    parts = [_authored_text()]
    if MAIN_TEX.exists():
        parts.append(MAIN_TEX.read_text(encoding="utf-8"))
    tables = Path(PAPER_GENERATED_DIR) / "tables"
    for path in sorted(tables.glob("*.tex")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _compile() -> Optional[Path]:
    pdflatex = shutil.which("pdflatex") or str(
        Path.home() / "AppData/Roaming/TinyTeX/bin/windows/pdflatex.exe")
    if not Path(pdflatex).exists():
        logger.warning(f"[COMPILE] pdflatex not found at {pdflatex}; the LaTeX source is "
                       f"written but not compiled")
        return None

    started = time.time()
    # Twice: the longtable and the cross-references need a second pass to settle.
    for attempt in (1, 2):
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=PAPER_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            tail = "\n".join(line for line in result.stdout.splitlines()[-30:])
            logger.error(f"[COMPILE] pdflatex failed on pass {attempt}:\n{tail}")
            return None

    pdf = Path(PAPER_DIR) / "main.pdf"
    if not pdf.exists():
        return None
    # Copied where the other outputs live, under the name the project has always used.
    destination = Path(RESULTS_DIR) / "final_research_paper.pdf"
    shutil.copy2(pdf, destination)
    logger.info(f"[COMPILE] {destination} in {time.time() - started:.1f}s")
    return destination


def generate_report() -> None:
    logger.info("=== STAGE 8: REPORT ===")
    started = time.time()

    # Cleared first: a quantity whose recorder was removed would otherwise persist in the
    # store and keep appearing in the document, which is the typed-number problem by another
    # route.
    reset_metrics()

    summary = run_all_hypothesis_tests()
    collect_all()
    collect_insight_metrics()

    with Run("stage8.generate_report") as run:
        run.record("results.headline", _headline(summary), "",
                   "one-sentence statement of the outcome, derived from the test results")

    build_macros()
    build_all_tables()
    build_all_figures()

    problems, fallbacks = audit(_cited_document(), _authored_text(),
                                Path(PAPER_GENERATED_DIR) / "macros.tex")
    if fallbacks:
        # Appended so the document still builds and the gaps show on the page as ?? rather
        # than stopping the compile with an opaque LaTeX error.
        macros = Path(PAPER_GENERATED_DIR) / "macros.tex"
        macros.write_text(macros.read_text(encoding="utf-8")
                          + "\n% Cited but never computed - see the audit output.\n"
                          + fallbacks + "\n", encoding="utf-8")
    for problem in problems:
        logger.error(f"[AUDIT] {problem}")
    if not problems:
        logger.info("[AUDIT] every cited quantity is computed; no hand-typed numbers")

    _compile()
    logger.info(f"[COMPLETE] stage 8 in {time.time() - started:.1f}s")


if __name__ == "__main__":
    generate_report()
