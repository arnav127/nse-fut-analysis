"""Integration tests: run the rewritten analysis queries against a synthetic enriched layer.

These build a tiny trade tape with a *known* price-impact coefficient and check that the
analyses recover it. That is the only way to catch the class of defect these queries had:
the old Kyle's lambda returned a number for every symbol and session, and the number was
near zero because the regressor was unsigned, not because impact was absent. Nothing short
of a case with a known answer distinguishes those two.
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

# The true coefficient the synthetic tape is generated with.
TRUE_LAMBDA = 0.0005
N_TRADES = 4000
SYMBOLS = ("AAA", "BBB")
SESSIONS = (("25012022", "2022-01-25"), ("27012022", "2022-01-27"))


def _tape(session: str, iso: str, rng: np.random.Generator) -> pd.DataFrame:
    frames = []
    for symbol, base in zip(SYMBOLS, (1000.0, 500.0)):
        sign = rng.choice([-1, 1], N_TRADES)
        qty = rng.integers(1, 500, N_TRADES)
        price = base + np.cumsum(TRUE_LAMBDA * sign * qty + rng.normal(0, 0.01, N_TRADES))
        ts = pd.Timestamp(f"{iso} 15:00:00") + pd.to_timedelta(np.arange(N_TRADES) * 0.4, unit="s")
        frames.append(pd.DataFrame({
            "symbol": symbol,
            "txn_time": ts,
            "txn_datetime": ts,
            "trade_price": price,
            "trade_quantity": qty.astype("uint64"),
            "buy_participant_type": rng.choice(["Custodian", "Proprietary", "NCNP"], N_TRADES),
            "sell_participant_type": rng.choice(["Custodian", "Proprietary", "NCNP"], N_TRADES),
            "record_indicator": "RM",
            "is_regular_market": True,
            "session": session,
            "trade_date": iso,
            "trade_time": ts.strftime("%H:%M:%S"),
            "time_bucket": ts.strftime("%H:%M:00"),
            "is_settlement_window": True,
            "is_expiry": session == "27012022",
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def enriched(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("enriched_layer")
    rng = np.random.default_rng(7)
    for session, iso in SESSIONS:
        for symbol, part in _tape(session, iso, rng).groupby("symbol"):
            out = root / "cash_trades" / f"date={session}" / f"sym={symbol}"
            out.mkdir(parents=True, exist_ok=True)
            part.to_parquet(out / "data.parquet", index=False)
    return root


@pytest.fixture
def results(tmp_path) -> Path:
    out = tmp_path / "results"
    out.mkdir()
    return out


class TestPriceImpact:
    def _run(self, enriched, results):
        from stage5_clob_analysis import b4_price_impact
        b4_price_impact.ENRICHED_DATA_DIR = enriched
        b4_price_impact.RESULTS_DIR = results
        b4_price_impact.EXPIRY_THURSDAYS_DDMMYYYY = ["27012022"]
        return b4_price_impact.run_b4_price_impact()

    def test_recovers_the_true_lambda(self, enriched, results):
        df = self._run(enriched, results)
        assert len(df) == len(SYMBOLS) * len(SESSIONS)
        assert (df.kyle_lambda > 0).all(), "signed flow must give a positive coefficient"
        for value in df.kyle_lambda:
            assert value == pytest.approx(TRUE_LAMBDA, rel=0.15)

    def test_fit_is_strong_on_data_generated_from_the_model(self, enriched, results):
        df = self._run(enriched, results)
        assert (df.kyle_r2 > 0.5).all()

    def test_expiry_flag_is_set_from_the_calendar(self, enriched, results):
        df = self._run(enriched, results).set_index(["symbol", "trade_date"])
        # The defect this guards: an ISO trade_date compared against a DDMMYYYY calendar
        # matched nothing and marked every session a control day.
        assert df.loc[("AAA", "2022-01-27"), "is_expiry"]
        assert not df.loc[("AAA", "2022-01-25"), "is_expiry"]


class TestParticipantProfile:
    def test_every_trade_counted_once_per_side(self, enriched, results):
        from stage3_analysis import a3_participant_profile
        a3_participant_profile.ENRICHED_DATA_DIR = enriched
        a3_participant_profile.RESULTS_DIR = results
        df = a3_participant_profile.run_a3_participant_profile()

        expected = N_TRADES * len(SYMBOLS) * len(SESSIONS)
        per_side = df.groupby("side").trades.sum()
        assert per_side["BUY"] == expected
        assert per_side["SELL"] == expected


class TestPairedTests:
    def test_pairs_each_symbol_with_itself_once(self, enriched, results, monkeypatch):
        from stage3_analysis import a3_participant_profile
        from stage5_clob_analysis import b4_price_impact
        from stage7_report import stat_tests

        for module in (a3_participant_profile,):
            module.ENRICHED_DATA_DIR = enriched
            module.RESULTS_DIR = results
        b4_price_impact.ENRICHED_DATA_DIR = enriched
        b4_price_impact.RESULTS_DIR = results
        b4_price_impact.EXPIRY_THURSDAYS_DDMMYYYY = ["27012022"]

        a3_participant_profile.run_a3_participant_profile()
        b4_price_impact.run_b4_price_impact()

        monkeypatch.setattr(stat_tests, "RESULTS_DIR", results)
        monkeypatch.setattr(stat_tests, "EXPIRY_CONTROL_PAIRS", [("27012022", "25012022")])
        summary = stat_tests.run_all_hypothesis_tests()

        tested = summary[summary.p_value.notna()]
        assert not tested.empty, "the two available inputs should yield tested hypotheses"
        # Two symbols, one expiry/control month: a correct pairing gives exactly two pairs.
        # The previous merge on symbol alone formed the cross product of every breakdown row
        # and would report hundreds.
        assert (tested.n_pairs == len(SYMBOLS)).all(), tested.n_pairs.tolist()
        assert (tested.n_months == 1).all()
