"""Quantities for the follow-up analyses: the next-morning reversal against news, the order
book through the expiry day and its volatility, fleeting orders and volatility, and the stock
futures.

Reads the CSVs written by stage9_tape.overnight_tests and stage9_tape.followups and records
each number the report cites.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402
from utils.provenance import Run  # noqa: E402

SPEC_KEY = {
    "baseline": "base",
    "without news days": "nonews",
    "beta-adjusted": "beta",
    "without 24 Feb 2022": "nofeb",
    "beta-adjusted, without news days": "betanonews",
    "earlier move (open to window)": "earlier",
    "window move, controlling earlier move": "ctrlearlier",
    "horizon: gap": "gap",
    "horizon: morning": "morning",
    "horizon: rest_of_day": "restofday",
    "horizon: next_day": "nextday",
}
MEASURE_KEY = {"d_spread": "spread", "d_depth": "depth", "d_rv": "rv",
               "abs_oib": "absoib", "window_share": "share", "abs_move": "absmove",
               "contract_share": "contractshare"}
PART_KEY = {"09:30-15:00": "day", "15:00-15:30": "window"}


def _csv(name: str) -> pd.DataFrame:
    path = Path(RESULTS_DIR) / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def collect_followup_metrics() -> None:
    with Run("stage9.followups") as run:
        for r in _csv("s11_overnight_robustness.csv").itertuples(index=False):
            spec = SPEC_KEY.get(r.spec)
            if spec is None:
                continue
            stem = f"news.{r.sample}.{spec}"
            run.record(stem, float(r.expiry), "ratio",
                       f"additional reversal on monthly expiries, {r.spec}, {r.sample}")
            run.record(f"{stem}.se", float(r.expiry_se), "ratio",
                       f"{r.spec}, {r.sample}; standard error clustered by session")
            run.record(f"{stem}.p", float(r.expiry_p), "p-value",
                       f"{r.spec}, {r.sample}; cluster-robust p-value")
        for r in _csv("s11_overnight_session_ri.csv").itertuples(index=False):
            run.record(f"news.sessionri.{r.set}", float(r.ri_p), "p-value",
                       "mean reversal slope over the expiries against means over one ordinary "
                       "session per month")
            run.record(f"news.sessionmean.{r.set}", float(r.expiry_mean), "ratio",
                       "mean of the per-expiry reversal slopes")
        slopes = _csv("s11_overnight_by_session.csv")
        if not slopes.empty:
            d = slopes[slopes.set == "derivative"]
            normal = d[d.day_type == "normal"].slope
            lo, hi = normal.quantile(0.05), normal.quantile(0.95)
            exp = d[d.day_type == "monthly_expiry"].slope
            run.record("news.expiries.inrange", int(((exp >= lo) & (exp <= hi)).sum()),
                       "expiries", "monthly expiries whose slope lies within the 5-95 per cent "
                       "range of ordinary sessions")
            run.record("news.normal.sessions", int(normal.size), "sessions",
                       "ordinary sessions in the per-session comparison")

        for r in _csv("s13_book_parts.csv").itertuples(index=False):
            stem = f"bookday.{PART_KEY[r.part]}.{r.group}.{MEASURE_KEY[r.measure]}"
            run.record(stem, float(r.mean), "per cent",
                       f"expiry minus control in log points, {r.part}, {r.group}")
            run.record(f"{stem}.p", float(r.p), "p-value", "paired t-test across stock-months")
        for r in _csv("s13_volatility_test.csv").itertuples(index=False):
            g = r.group.replace("all F&O", "fo")
            stem = f"voltest.{g}.{MEASURE_KEY[r.measure]}"
            run.record(f"{stem}.raw", float(r.raw_mean), "per cent",
                       "window change, expiry minus control")
            run.record(f"{stem}.slope", float(r.slope_rv), "ratio",
                       "slope on the change in log realised variance")
            run.record(f"{stem}.slope.se", float(r.slope_se), "ratio", "standard error")
            run.record(f"{stem}.intercept", float(r.intercept), "per cent",
                       "change at unchanged realised variance")
            run.record(f"{stem}.intercept.se", float(r.intercept_se), "per cent",
                       "standard error")
            run.record(f"{stem}.intercept.p", float(r.intercept_p), "p-value", "")
            run.record(f"{stem}.explained", 100 * (1 - float(r.intercept) / float(r.raw_mean)),
                       "per cent", "share of the raw change accounted for by volatility")
        for r in _csv("s13_fleeting_volatility.csv").itertuples(index=False):
            stem = f"fleetvol.{r.group}"
            run.record(f"{stem}.raw", float(r.raw_mean_pp), "per cent",
                       "change in the share of orders cancelled within a second")
            # Per ten log points of variance, so that the slope reads at two decimals.
            run.record(f"{stem}.slope", 10 * float(r.slope_rv), "ratio",
                       "change in percentage points per ten per cent rise in realised variance")
            run.record(f"{stem}.slope.se", 10 * float(r.slope_se), "ratio", "standard error")
            run.record(f"{stem}.intercept", float(r.intercept_pp), "per cent",
                       "change at unchanged realised variance")
            run.record(f"{stem}.intercept.se", float(r.intercept_se), "per cent",
                       "standard error")
        for r in _csv("s13_futures_tape.csv").itertuples(index=False):
            stem = f"futtape.{r.contract}.{MEASURE_KEY[r.measure]}"
            unit = "ratio" if r.measure == "abs_oib" else "per cent" if "share" in r.measure \
                else "basis points"
            run.record(f"{stem}.control", float(r.control), unit, "day before expiry")
            run.record(f"{stem}.expiry", float(r.expiry), unit, "expiry day")
            run.record(f"{stem}.diff", float(r.mean), unit, "paired difference")
            run.record(f"{stem}.p", float(r.p), "p-value", "paired t-test")
        for r in _csv("s13_futures_book.csv").itertuples(index=False):
            stem = f"futbook.{r.market}.{PART_KEY[r.part]}.{MEASURE_KEY[r.measure]}"
            run.record(stem, float(r.mean), "per cent",
                       f"expiry minus control in log points, {r.market}, {r.part}")
            run.record(f"{stem}.p", float(r.p), "p-value", "paired t-test across stock-months")
            run.record(f"{stem}.n", int(r.n), "stock-months", "")


if __name__ == "__main__":
    collect_followup_metrics()
