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
        for r in _csv("s13_futures_voltest.csv").itertuples(index=False):
            stem = f"futvol.{MEASURE_KEY[r.measure]}"
            run.record(f"{stem}.slope", float(r.slope_rv), "ratio",
                       "expiring future, slope on the change in log realised variance")
            run.record(f"{stem}.slope.se", float(r.slope_se), "ratio", "standard error")
            run.record(f"{stem}.intercept", float(r.intercept), "per cent",
                       "expiring future, change at unchanged realised variance")
            run.record(f"{stem}.intercept.se", float(r.intercept_se), "per cent",
                       "standard error")
            run.record(f"{stem}.intercept.p", float(r.intercept_p), "p-value", "")
            run.record(f"{stem}.explained", 100 * (1 - float(r.intercept) / float(r.raw_mean)),
                       "per cent", "share of the raw change accounted for by volatility")
        books = sorted((Path(RESULTS_DIR) / "futures_book").glob("session=*.parquet"))
        if books:
            fb = pd.concat([pd.read_parquet(f, columns=["symbol", "market", "session"])
                            for f in books])
            fut = fb[fb.market == "futures"].groupby("session").symbol.nunique()
            run.record("futbook.securities", int(fut.max()), "securities",
                       "stock futures with a reconstructed book on a session")
            run.record("futbook.securities.min", int(fut.min()), "securities",
                       "fewest stock futures with a reconstructed book on a session")
        for r in _csv("s13_futures_book.csv").itertuples(index=False):
            stem = f"futbook.{r.market}.{PART_KEY[r.part]}.{MEASURE_KEY[r.measure]}"
            run.record(stem, float(r.mean), "per cent",
                       f"expiry minus control in log points, {r.market}, {r.part}")
            run.record(f"{stem}.p", float(r.p), "p-value", "paired t-test across stock-months")
            run.record(f"{stem}.n", int(r.n), "stock-months", "")

        # BH2 as a panel with stock fixed effects.
        for r in _csv("s16_bh2_panel.csv").itertuples(index=False):
            part = "window" if r.part == "window" else "day"
            y = "spread" if r.y == "log_spread" else "depth"
            ctrl = "vol" if str(r.vol_control) == "True" else "raw"
            stem = f"panel.{part}.{y}.{ctrl}.{r.sample}"
            run.record(stem, float(r.coef), "per cent", f"expiry coefficient, {r.sample}")
            run.record(f"{stem}.se", float(r.se), "per cent", "clustered by stock")
            run.record(f"{stem}.p", float(r.p), "p-value", "")
            run.record(f"{stem}.n", int(r.nobs), "observations", "stock-sessions")

        # Where the placebo stocks sit in the market.
        summary = _csv("s17_placebo_summary.csv")
        for r in summary.itertuples(index=False):
            stem = f"placebocheck.{r.group}"
            run.record(f"{stem}.n500", int(r.n500_2022), "securities",
                       "members of the Nifty 500 in October 2022")
            run.record(f"{stem}.n500either", int(r.n500_either), "securities",
                       "members of the Nifty 500 in July 2020 or February 2024")
            run.record(f"{stem}.rankmedian", int(round(float(r.rank_median))), "securities",
                       "median rank by turnover among all equities")
            run.record(f"{stem}.rankmin", int(r.rank_min), "securities", "highest rank")
            run.record(f"{stem}.rankmax", int(r.rank_max), "securities", "lowest rank")
            run.record(f"{stem}.turnover", float(r.turnover_median_cr), "ratio",
                       "median turnover over the order book sample, crore")
        if not summary.empty:
            run.record("placebocheck.market", int(summary.market_stocks.iloc[0]), "securities",
                       "equities traded on the order book sample's sessions")

        # The hedge-unwinding tests.
        oi = _csv("s18_expiring_oi.csv")
        if not oi.empty:
            run.record("hedge.expiries", int(len(oi)), "sessions", "index expiries with open "
                       "interest on the session before")
            run.record("hedge.optoi", float(oi.opt_oi_cr.median()) / 1e5, "ratio",
                       "median expiring Nifty option open interest, lakh crore notional")
            run.record("hedge.pcr", float(oi.pcr.median()), "ratio",
                       "median put-call ratio of expiring open interest")
            monthly = oi[oi.monthly == 1]
            run.record("hedge.futoi", float(monthly.fut_oi_cr.median()) / 1e3, "ratio",
                       "median expiring Nifty futures open interest on monthly expiries, "
                       "thousand crore")
        for r in _csv("s18_oi_regressions.csv").itertuples(index=False):
            stem = f"hedge.oireg.{r.x.replace('_', '')}"
            run.record(stem, float(r.slope_per_sd), "basis points",
                       "change in the index's relative window move per standard deviation")
            run.record(f"{stem}.se", float(r.se), "basis points", "robust standard error")
            run.record(f"{stem}.p", float(r.p), "p-value", "")
            run.record(f"{stem}.n", int(r.n), "sessions", "")
        for r in _csv("s18_cash_flows.csv").itertuples(index=False):
            sample = {"Nifty 50 stocks": "nifty", "other F&O stocks": "otherfo",
                      "placebo": "placebo"}[r.sample]
            stem = f"hedge.flow.{sample}.{r.y.replace('_', '')}"
            run.record(stem, float(r.coef), "ratio",
                       "index-expiry change in net aggressor flow, per cent of median volume")
            run.record(f"{stem}.se", float(r.se), "ratio", "clustered by session")
            run.record(f"{stem}.p", float(r.p), "p-value", "")
            run.record(f"hedge.flow.{sample}.stocks", int(r.stocks), "securities", "")
        pos = _csv("s18_positions.csv")
        if not pos.empty:
            med = pos.groupby("who").median(numeric_only=True)
            for who in med.index:
                for col in ("fut_net_before", "call_net_before", "put_net_before",
                            "call_net_change", "put_net_change"):
                    run.record(f"hedge.pos.{who.lower()}.{col.replace('_', '')}",
                               float(med.loc[who, col]) / 1e3, "ratio",
                               f"median index derivatives position of {who}, thousand "
                               f"contracts, session before an index expiry")
        preg = _csv("s18_position_regressions.csv")
        if not preg.empty:
            run.record("hedge.posreg.minp", float(preg.p.min()), "p-value",
                       "smallest p-value among the regressions of the index move on positions")
            run.record("hedge.posreg.n", int(preg.n.max()), "sessions", "")
        deriv = _csv("s18_index_deriv_flows.csv")
        if not deriv.empty:
            w = deriv[(deriv.in_window == True) & (deriv.expiring == True)]  # noqa: E712
            run.record("hedge.deriv.sessions", int(deriv.session.nunique()), "sessions",
                       "sessions with index derivatives trades reduced")
            for kind in ("calls", "puts", "futures"):
                for flag, name in ((True, "expiry"), (False, "control")):
                    sub = w[(w.kind == kind) & (w.is_expiry == flag)]
                    if sub.empty:
                        continue
                    run.record(f"hedge.deriv.{kind}.{name}.share", float(sub.share_of_day.mean()),
                               "per cent", "window share of the contract's volume")
                    run.record(f"hedge.deriv.{kind}.{name}.net",
                               float(sub.net_aggressor.mean()) / 1e5, "ratio",
                               "net aggressor buying in the window, lakh units")
                    run.record(f"hedge.deriv.{kind}.{name}.prop",
                               float(sub.prop_net.mean()) / 1e5, "ratio",
                               "net buying by proprietary accounts in the window, lakh units")


if __name__ == "__main__":
    collect_followup_metrics()
