"""Tests for the pieces that produce a plausible wrong number when they break.

Everything here is a case where the previous implementation returned something - a p-value,
a lambda, a shock count - rather than failing, which is why each is pinned rather than left
to the end-to-end run to catch.

    python -m pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage8_report.stat_tests import _benjamini_hochberg, _session_level  # noqa: E402
from utils.paths import iso_to_session, session_to_iso  # noqa: E402


class TestDateSpellings:
    """The mismatch that silently classified every session as a control day."""

    def test_round_trip(self):
        assert session_to_iso("27012022") == "2022-01-27"
        assert iso_to_session("2022-01-27") == "27012022"

    def test_day_and_month_are_not_transposed(self):
        # 03/11 and 11/03 both parse under a lenient format; only one is right.
        assert session_to_iso("03112022") == "2022-11-03"

    def test_rejects_an_iso_string(self):
        with pytest.raises(ValueError):
            session_to_iso("2022-01-27")


class TestBenjaminiHochberg:
    def test_step_up_rejects_everything_below_the_largest_passing_rank(self):
        # p3 = 0.04 clears 3/4 * 0.05 = 0.0375? No - but p4 = 0.045 does not clear 0.05
        # either. The point is the monotonicity: whatever the cutoff, the rejected set is a
        # prefix of the sorted p-values.
        p = np.array([0.001, 0.03, 0.04, 0.9])
        reject = _benjamini_hochberg(p, 0.05)
        assert reject.dtype == bool
        ranked = np.argsort(p)
        rejected_ranks = [i for i, idx in enumerate(ranked) if reject[idx]]
        assert rejected_ranks == list(range(len(rejected_ranks))), "rejections must be a prefix"

    def test_a_larger_p_never_rejects_while_a_smaller_one_does_not(self):
        # The defect in the element-wise version: p = 0.02 fails 1/3 * 0.05 but p = 0.03
        # clears 2/3 * 0.05, so the naive rule rejects the larger and not the smaller.
        p = np.array([0.02, 0.03, 0.9])
        reject = _benjamini_hochberg(p, 0.05)
        assert reject[0] or not reject[1], "cannot reject 0.03 while leaving 0.02 standing"
        assert list(reject) == [True, True, False]

    def test_nothing_passes(self):
        assert not _benjamini_hochberg(np.array([0.4, 0.6, 0.99]), 0.05).any()

    def test_everything_passes(self):
        assert _benjamini_hochberg(np.array([1e-6, 2e-6, 3e-6]), 0.05).all()

    def test_empty(self):
        assert _benjamini_hochberg(np.array([]), 0.05).size == 0


class TestSessionLevelReduction:
    """The many-to-many pairing: several rows per symbol-session must collapse to one."""

    def _frame(self):
        return pd.DataFrame({
            "symbol": ["RELIANCE"] * 4 + ["TCS"] * 2,
            "trade_date": ["2022-01-27"] * 4 + ["2022-01-27"] * 2,
            "time_bucket": ["15:00:00", "15:01:00", "15:02:00", "15:03:00",
                            "15:00:00", "15:01:00"],
            "participant_type": ["Custodian", "Proprietary", "Custodian", "NCNP",
                                 "Custodian", "NCNP"],
            "rate": [0.1, 0.2, 0.3, 0.4, 1.0, 3.0],
            "count": [1, 2, 3, 4, 10, 30],
        })

    def test_one_row_per_symbol_session(self):
        out = _session_level(self._frame(), "rate", "mean")
        assert len(out) == 2
        assert set(out.symbol) == {"RELIANCE", "TCS"}

    def test_mean_reduces_rates(self):
        out = _session_level(self._frame(), "rate", "mean").set_index("symbol")["rate"]
        assert out["RELIANCE"] == pytest.approx(0.25)
        assert out["TCS"] == pytest.approx(2.0)

    def test_sum_reduces_counts(self):
        out = _session_level(self._frame(), "count", "sum").set_index("symbol")["count"]
        assert out["RELIANCE"] == 10
        assert out["TCS"] == 40

    def test_row_filter_narrows_before_reducing(self):
        out = _session_level(self._frame(), "rate", "mean",
                             row_filter=("participant_type", "Custodian")).set_index("symbol")
        assert out.loc["RELIANCE", "rate"] == pytest.approx(0.2)
        assert out.loc["TCS", "rate"] == pytest.approx(1.0)

    def test_missing_filter_column_yields_nothing_rather_than_everything(self):
        # Silently ignoring an unknown filter would test the wrong hypothesis.
        assert _session_level(self._frame(), "rate", "mean",
                              row_filter=("sub_window", "Late")).empty

    def test_infinities_are_dropped(self):
        frame = self._frame()
        frame.loc[0, "rate"] = np.inf
        out = _session_level(frame, "rate", "mean").set_index("symbol")["rate"]
        assert np.isfinite(out["RELIANCE"])
        assert out["RELIANCE"] == pytest.approx(0.3)


def _collapse_episodes(elevated: np.ndarray) -> np.ndarray:
    """The episode-start rule from B7, isolated so it can be pinned."""
    return np.flatnonzero(elevated & ~np.r_[False, elevated[:-1]])


class TestShockEpisodes:
    def test_a_run_of_elevated_seconds_is_one_shock(self):
        elevated = np.array([False, True, True, True, False, False])
        assert _collapse_episodes(elevated).tolist() == [1]

    def test_separate_runs_are_separate_shocks(self):
        elevated = np.array([True, True, False, True, False, True])
        assert _collapse_episodes(elevated).tolist() == [0, 3, 5]

    def test_no_shock(self):
        assert _collapse_episodes(np.zeros(5, dtype=bool)).size == 0

    def test_entirely_elevated_is_one_shock(self):
        assert _collapse_episodes(np.ones(5, dtype=bool)).tolist() == [0]


class TestTickRuleSigning:
    """Kyle's lambda needs signed flow; unsigned volume makes it identically near zero."""

    def test_unsigned_volume_cancels(self):
        rng = np.random.default_rng(0)
        qty = rng.integers(1, 1000, 5000).astype(float)
        sign = rng.choice([-1.0, 1.0], 5000)
        # Price change is genuinely proportional to *signed* flow.
        px = 0.002 * sign * qty + rng.normal(0, 0.01, 5000)

        unsigned = np.cov(px, qty)[0, 1] / np.var(qty, ddof=1)
        signed = np.cov(px, sign * qty)[0, 1] / np.var(sign * qty, ddof=1)

        assert abs(unsigned) < 1e-3, "unsigned regressor recovers no impact"
        assert signed == pytest.approx(0.002, rel=0.1), "signed regressor recovers lambda"


class TestRealisedVarianceRate:
    """H24 compares a 30-minute window with a ~345-minute one."""

    def test_summed_ratio_is_dominated_by_window_length(self):
        rng = np.random.default_rng(1)
        settlement = rng.normal(0, 0.001, 30)
        presettlement = rng.normal(0, 0.001, 345)

        summed = (settlement ** 2).sum() / (presettlement ** 2).sum()
        per_minute = (settlement ** 2).mean() / (presettlement ** 2).mean()

        assert summed < 0.25, "equal variance rates still score far below 1 when summed"
        assert per_minute == pytest.approx(1.0, abs=0.5), "per-minute rate is near 1"
