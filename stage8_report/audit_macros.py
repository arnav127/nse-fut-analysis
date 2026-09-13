r"""Check the manuscript against the recorded metrics before it is compiled.

Two failures this catches, both of which otherwise reach the PDF looking fine.

*A cited quantity that was never recorded.* LaTeX would stop with "undefined control
sequence", or worse, typeset nothing at all if the name happened to be defined empty. The
audit defines any missing name as a visible \textbf{??} so the document still builds and the
gap is obvious on the page, and reports it as a failure.

*A hand-typed number in the prose.* The point of the macro layer is that no figure is typed
in. A numeral in the authored text is therefore a defect, and this finds it rather than
trusting that nobody did it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Audit", "stage8_report.log")

# A generated macro is a capitalised name of at least four letters called with empty braces.
# That shape distinguishes them from LaTeX's own commands without maintaining a list of those.
CITATION = re.compile(r"\\([A-Z][A-Za-z]{3,})\{\}")

# Lines whose numerals are typography rather than content.
EXEMPT_LINE = re.compile(
    r"documentclass|usepackage|geometry|RGB|includegraphics|width=|vspace|hspace"
    r"|setlength|columnwidth|textwidth|begin\{tabular\}|begin\{longtable\}"
    r"|captionsetup|newcommand|providecommand|^\s*%"
)

# Terminology and definitions whose digits name a thing rather than measure one. Fixed
# strings, not patterns: an expression broad enough to classify numerals by shape would also
# exempt the findings, which is the opposite of what this check exists for.
#
# Small integers in the prose are spelled out in words - "thirty minutes", "two features" -
# so there is no need to exempt them, and requiring that is what keeps this list short.
EXEMPT_PHRASES = (
    "Level 3",        # the name of the feed
    "1/65536",        # the jiffy definition, quoted from the exchange specification
    "65536",
    "1980-01-01",     # the jiffy epoch
    "1.5",            # the recovery threshold, defined in the sentence that uses it
    "95\\%",          # the confidence level of the plotted intervals
)

# A year is a date, not a result.
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
NUMERAL = re.compile(r"(?<![\w\\])\d[\d,.]*")


def defined_macros(macros_tex: Path) -> Set[str]:
    if not macros_tex.exists():
        return set()
    body = macros_tex.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"\\(?:new|provide)command\{\\([A-Za-z]+)\}", body))


COMMENT = re.compile(r"(?<!\\)%.*$", re.MULTILINE)


def strip_comments(text: str) -> str:
    """Remove LaTeX comments, respecting an escaped percent sign.

    The manuscript's header comments explain the macro convention by example, and a citation
    scanner that reads comments reports those examples as quantities that were never
    computed.
    """
    return COMMENT.sub("", text)


def cited_macros(*sources: str) -> Set[str]:
    names: Set[str] = set()
    for text in sources:
        names |= set(CITATION.findall(strip_comments(text)))
    return names


def hand_typed_numbers(authored_text: str) -> List[Tuple[int, str]]:
    """Numerals in the authored prose, which should contain none."""
    offenders: List[Tuple[int, str]] = []
    for line_number, line in enumerate(authored_text.splitlines(), 1):
        if EXEMPT_LINE.search(line):
            continue
        stripped = line
        for phrase in EXEMPT_PHRASES:
            stripped = stripped.replace(phrase, "")
        stripped = YEAR.sub("", stripped)
        if NUMERAL.search(stripped):
            offenders.append((line_number, line.strip()[:110]))
    return offenders


def audit(document: str, authored_text: str, macros_tex: Path) -> Tuple[List[str], str]:
    """Returns (problems, LaTeX defining any missing macro as a visible marker)."""
    problems: List[str] = []

    defined = defined_macros(macros_tex)
    cited = cited_macros(document)
    missing = sorted(cited - defined)
    if missing:
        problems.append(
            f"{len(missing)} quantities are cited but never recorded: "
            + ", ".join(missing[:12]) + ("..." if len(missing) > 12 else ""))

    unused = sorted(defined - cited)
    if unused:
        # Not a failure. Recording more than the text cites is normal - the store is also
        # the audit trail - but the count is worth seeing in the log.
        logger.info(f"[AUDIT] {len(unused)} recorded quantities are not cited in the text")

    for line_number, line in hand_typed_numbers(authored_text):
        problems.append(f"hand-typed number in the manuscript text, line {line_number}: {line}")

    fallbacks = "\n".join(rf"\providecommand{{\{name}}}{{\textbf{{??}}}}" for name in missing)
    return problems, fallbacks


if __name__ == "__main__":
    from config.settings import RESULTS_DIR
    from stage8_report.generate_report import _authored_text

    tex = Path(RESULTS_DIR) / "final_research_paper.tex"
    if not tex.exists():
        print("no manuscript to audit; run the report stage first", file=sys.stderr)
        raise SystemExit(1)
    issues, _ = audit(tex.read_text(encoding="utf-8"), _authored_text(),
                      Path(RESULTS_DIR) / "macros.tex")
    for issue in issues:
        print(issue)
    print("clean" if not issues else f"{len(issues)} problems")
    raise SystemExit(1 if issues else 0)
