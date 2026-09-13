"""Tests for the layer that keeps typed numbers out of the manuscript.

The macro chain fails quietly when it fails at all: a mangled name produces an undefined
command, a collision gives the document whichever value was written last, and a mis-chosen
format turns Kyle's lambda into "0.00". Each of those is pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage7_report.audit_macros import (  # noqa: E402
    audit, cited_macros, defined_macros, hand_typed_numbers,
)
from stage7_report.build_macros import format_value, macro_name  # noqa: E402


class TestMacroNames:
    def test_dotted_key_becomes_camel_case(self):
        assert macro_name("spread.mean_bps_expiry") == "SpreadMeanBpsExpiry"

    def test_digits_are_spelled_out(self):
        # LaTeX command names cannot contain digits, so H12 cannot be \HH12PValue.
        assert macro_name("h.h12.p_value") == "HHOneTwoPValue"
        assert macro_name("design.book_levels") == "DesignBookLevels"

    def test_name_is_letters_only(self):
        for key in ("h.h30.effect_size_cohen_d", "sample.order_events_millions",
                    "test.rejected_fdr", "ice.ratio_diff"):
            assert macro_name(key).isalpha(), key

    def test_separators_are_equivalent(self):
        assert macro_name("a.b_c") == macro_name("a-b.c") == "ABC"

    def test_distinct_keys_give_distinct_names(self):
        keys = ["spread.mean_bps_expiry", "spread.mean_bps_control", "spread.mean_bps_diff",
                "spread.max_bps_expiry", "h.h1.p_value", "h.h10.p_value", "h.h11.p_value"]
        names = [macro_name(k) for k in keys]
        assert len(set(names)) == len(names), names


class TestFormatting:
    def test_fractions_render_as_percentages(self):
        assert format_value(0.1642, "fraction") == "16.42"

    def test_counts_get_thousands_separators(self):
        assert format_value(178627223, "") == "178,627,223"
        assert format_value(45184.0, "shares") == "45,184"

    def test_kyle_lambda_keeps_its_magnitude(self):
        # Two decimals would print this as 0.00, which reads as no impact.
        rendered = format_value(0.000487, "rupees per share")
        assert rendered not in ("0.00", "0"), rendered
        assert float(rendered) == pytest.approx(0.000487, rel=0.01)

    def test_basis_points_are_two_decimals(self):
        assert format_value(1.5832, "basis points") == "1.58"

    def test_strings_are_escaped(self):
        assert format_value("50% of R&D", "") == r"50\% of R\&D"

    def test_integers_are_not_given_decimals(self):
        assert format_value(24, "sessions") == "24"


class TestAudit:
    def test_finds_a_cited_but_unrecorded_quantity(self, tmp_path):
        macros = tmp_path / "macros.tex"
        macros.write_text(r"\newcommand{\SpreadMeanBpsExpiry}{1.58}", encoding="utf-8")
        document = r"The spread was \SpreadMeanBpsExpiry{} against \SpreadMeanBpsControl{}."
        problems, fallbacks = audit(document, "", macros)
        assert any("SpreadMeanBpsControl" in p for p in problems)
        # The fallback keeps the document compiling with a visible marker.
        assert r"\providecommand{\SpreadMeanBpsControl}{\textbf{??}}" in fallbacks

    def test_passes_when_everything_is_recorded(self, tmp_path):
        macros = tmp_path / "macros.tex"
        macros.write_text(r"\newcommand{\DesignSessions}{24}", encoding="utf-8")
        problems, fallbacks = audit(r"Across \DesignSessions{} sessions.", "", macros)
        assert problems == []
        assert fallbacks == ""

    def test_ignores_ordinary_latex_commands(self):
        # \section and \textbf must not be mistaken for missing quantities.
        assert cited_macros(r"\section{Data} \textbf{bold} \DesignSessions{}") == {"DesignSessions"}

    def test_reads_both_newcommand_and_providecommand(self, tmp_path):
        macros = tmp_path / "macros.tex"
        macros.write_text("\\newcommand{\\Alpha}{1}\n\\providecommand{\\Beta}{2}\n",
                          encoding="utf-8")
        assert defined_macros(macros) == {"Alpha", "Beta"}


class TestHandTypedNumbers:
    def test_flags_a_typed_result(self):
        text = "The mean spread widened to 2.41 basis points on expiry sessions."
        assert len(hand_typed_numbers(text)) == 1

    def test_accepts_the_macro_form(self):
        text = r"The mean spread widened to \SpreadMeanBpsExpiry{} basis points."
        assert hand_typed_numbers(text) == []

    def test_allows_terminology_and_years(self):
        for line in ("These are Level 3 records, not aggregated depth.",
                     "All sessions fall in 2022.",
                     "Timestamps count 1/65536 second intervals from 1980-01-01."):
            assert hand_typed_numbers(line) == [], line

    def test_allows_numbers_spelled_out(self):
        assert hand_typed_numbers("a window of thirty minutes ending at the close") == []

    def test_skips_typography(self):
        assert hand_typed_numbers(r"\includegraphics[width=0.82\textwidth]{fig.png}") == []


class TestManuscriptIsClean:
    def test_the_authored_prose_contains_no_typed_numbers(self):
        from stage7_report.generate_report import _authored_text
        offenders = hand_typed_numbers(_authored_text())
        assert offenders == [], offenders

    def test_every_cited_name_is_spelled_the_way_a_key_would_be(self):
        from stage7_report import manuscript
        text = "\n".join(v for k, v in vars(manuscript).items()
                         if isinstance(v, str) and not k.startswith("__"))
        for name in cited_macros(text):
            assert name.isalpha() and name[0].isupper(), name


class TestPValueRendering:
    """A p-value below 1e-4 is math-mode content cited from text-mode table cells."""

    def test_small_p_values_are_safe_outside_math_mode(self):
        from stage7_report.build_macros import _p_value
        rendered = _p_value(1.7e-5)
        # A bare \times outside maths is a fatal LaTeX error, not a formatting wobble.
        assert rendered.startswith(r"\ensuremath{"), rendered
        assert r"\times" in rendered

    def test_ordinary_p_values_are_plain_decimals(self):
        from stage7_report.build_macros import _p_value
        assert _p_value(0.0312) == "0.0312"
        assert _p_value(0.9) == "0.9000"

    def test_exponent_is_preserved(self):
        from stage7_report.build_macros import _p_value
        assert "10^{-12}" in _p_value(3.2e-12)
