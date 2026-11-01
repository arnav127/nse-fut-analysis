"""Is the fall of the index settlement the unwinding of hedges?

If traders who hold Nifty 50 stocks against index derivatives (arbitrageurs long the stocks and
short futures, or option writers hedged in the stocks) close the stock side in the settlement
window, then:

  open interest  the fall should be larger on expiries on which more open interest expires;
  cash flow      Nifty 50 stocks should see net aggressive selling in the window on index
                 expiries, from the participant categories that run such books;
  derivatives    the expiring index derivatives should be closed or settled, not traded in
                 the window in the same direction.

Inputs: the index panel (s10_index_panel.csv), the NSE F&O bhavcopies (open interest, in
data/external/bhav), the stock panel (s9_panel.parquet), the Nifty 50 list of July 2022, and the
index derivatives trades (s14_index_deriv/). Output: data/results/s18_*.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import EXPIRY_CONTROL_PAIRS, RESULTS_DIR  # noqa: E402
from utils.panel import fe_ols  # noqa: E402

RES = Path(RESULTS_DIR)
EXT = PROJECT_ROOT / "data" / "external"
PARTS = ["custodian", "proprietary", "ncnp"]


def index_moves() -> pd.DataFrame:
    """Window move of Nifty 50 minus Nifty Next 50 per session, in basis points."""
    path = RES / "s10_index_panel.csv"
    if not path.exists():
        path = PROJECT_ROOT / "data" / "results_hpc" / "s10_index_panel.csv"
    p = pd.read_csv(path, dtype={"session": str, "next_session": str})
    wide = p.pivot_table(index=["session", "expiry", "monthly", "month_end"], columns="index",
                         values=["drift", "move", "next_rev"]).reset_index()
    wide.columns = ["_".join(c).strip("_") for c in wide.columns]
    for v in ("drift", "move", "next_rev"):
        wide[f"rel_{v}"] = wide[f"{v}_nifty"] - wide[f"{v}_next50"]
    return wide


def load_bhav() -> pd.DataFrame:
    frames = []
    for f in sorted((EXT / "bhav").glob("fo*bhav.csv")):
        b = pd.read_csv(f)
        b = b[b.SYMBOL == "NIFTY"]
        frames.append(b)
    b = pd.concat(frames, ignore_index=True)
    b["date"] = pd.to_datetime(b.TIMESTAMP, format="%d-%b-%Y")
    b["expiry"] = pd.to_datetime(b.EXPIRY_DT, format="%d-%b-%Y")
    return b


def expiring_oi(bhav: pd.DataFrame, moves: pd.DataFrame) -> pd.DataFrame:
    """Open interest on the session before each index expiry, in the series that expire."""
    sessions = sorted(bhav.date.unique())
    rows = []
    for _, m in moves[moves.expiry == 1].iterrows():
        day = pd.Timestamp(f"{m.session[4:]}-{m.session[2:4]}-{m.session[:2]}")
        before = [d for d in sessions if d < day]
        if not before:
            continue
        prev = bhav[(bhav.date == before[-1]) & (bhav.expiry == day)]
        if prev.empty:
            continue
        fut = prev[prev.INSTRUMENT == "FUTIDX"]
        opt = prev[prev.INSTRUMENT == "OPTIDX"]
        spot = float(fut.SETTLE_PR.iloc[0]) if not fut.empty else float(
            opt.loc[opt.OPEN_INT.idxmax(), "STRIKE_PR"])
        near = opt[(opt.STRIKE_PR - spot).abs() <= 0.02 * spot]
        calls, puts = opt[opt.OPTION_TYP == "CE"], opt[opt.OPTION_TYP == "PE"]
        rows.append({
            "session": m.session, "monthly": m.monthly, "rel_drift": m.rel_drift,
            "rel_move": m.rel_move, "rel_next_rev": m.rel_next_rev, "spot": spot,
            # Open interest is in units of the index; notional in crore of rupees.
            "fut_oi_cr": float(fut.OPEN_INT.sum()) * spot / 1e7,
            "call_oi_cr": float(calls.OPEN_INT.sum()) * spot / 1e7,
            "put_oi_cr": float(puts.OPEN_INT.sum()) * spot / 1e7,
            "near_oi_cr": float(near.OPEN_INT.sum()) * spot / 1e7,
            "near_put_minus_call_cr": float(near[near.OPTION_TYP == "PE"].OPEN_INT.sum()
                                            - near[near.OPTION_TYP == "CE"].OPEN_INT.sum())
                                       * spot / 1e7,
        })
    out = pd.DataFrame(rows)
    out["opt_oi_cr"] = out.call_oi_cr + out.put_oi_cr
    out["pcr"] = out.put_oi_cr / out.call_oi_cr
    return out


def oi_regressions(oi: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for x in ("opt_oi_cr", "near_oi_cr", "pcr", "near_put_minus_call_cr", "fut_oi_cr"):
        sub = oi.dropna(subset=[x, "rel_drift"])
        if x == "fut_oi_cr":
            sub = sub[sub.monthly == 1]
        if len(sub) < 8 or sub[x].std() == 0:
            continue
        z = (sub[x] - sub[x].mean()) / sub[x].std()
        X = np.column_stack([np.ones(len(sub)), z])
        beta, *_ = np.linalg.lstsq(X, sub.rel_drift, rcond=None)
        resid = sub.rel_drift - X @ beta
        # Heteroskedasticity-robust standard errors.
        bread = np.linalg.inv(X.T @ X)
        meat = (X * resid.to_numpy()[:, None] ** 2).T @ X
        se = np.sqrt(np.diag(bread @ meat @ bread))
        from scipy import stats
        rows.append({"x": x, "n": len(sub), "slope_per_sd": beta[1], "se": se[1],
                     "p": float(2 * stats.t.sf(abs(beta[1] / se[1]), len(sub) - 2)),
                     "corr": float(np.corrcoef(sub[x], sub.rel_drift)[0, 1])})
    return pd.DataFrame(rows)


def cash_flow_tests() -> pd.DataFrame:
    """Net aggressor flow by participant in the window, Nifty 50 stocks, index expiries."""
    panel = pd.read_parquet(RES / "s9_panel.parquet")
    nifty50 = set(pd.read_csv(EXT / "nifty50_2022.csv").Symbol)
    panel["n50"] = panel.symbol.isin(nifty50)
    panel["weekly_only"] = panel.weekly_expiry
    rows = []
    for sample, frame in (("Nifty 50 stocks", panel[panel.n50]),
                          ("other F&O stocks", panel[~panel.n50 & (panel.group != "placebo")]),
                          ("placebo", panel[panel.group == "placebo"])):
        for y in ["flow", *[f"flow_{p}" for p in PARTS]]:
            fit = fe_ols(frame, y, ["index_expiry", "month_end"], fe="symbol")
            if fit is None:
                continue
            rows.append({"sample": sample, "y": y, **fit.get("index_expiry"),
                         "nobs": fit.nobs, "stocks": frame.symbol.nunique()})
    return pd.DataFrame(rows)


def derivative_flows() -> pd.DataFrame:
    """Index futures and options in the window: expiry against the day before."""
    files = sorted((RES / "s14_index_deriv").glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    expiries = {e for e, _ in EXPIRY_CONTROL_PAIRS}
    d["is_expiry"] = d.session.isin(expiries)
    d["kind"] = np.where(d.instrument == "FUTIDX", "futures",
                         np.where(d.option_type == "CE", "calls", "puts"))
    g = d.groupby(["session", "is_expiry", "kind", "expiring", "in_window"]).agg(
        volume=("volume", "sum"), net_aggressor=("net_aggressor", "sum"),
        prop_net=("prop_net", "sum"), custodian_net=("custodian_net", "sum")).reset_index()
    day = g.groupby(["session", "kind", "expiring"]).volume.transform("sum")
    g["share_of_day"] = 100 * g.volume / day
    return g


def participant_oi() -> pd.DataFrame:
    """Index derivatives positions by participant category, from NSE's daily file.

    Contracts across all index derivatives (not only the Nifty 50). Net futures is long minus
    short; net options is long minus short calls and puts separately.
    """
    rows = []
    for f in sorted((EXT / "poi").glob("fao_participant_oi_*.csv")):
        session = f.stem.split("_")[-1]
        t = pd.read_csv(f, skiprows=1)
        t.columns = [c.strip() for c in t.columns]
        for _, r in t.iterrows():
            who = str(r["Client Type"]).strip()
            if who == "TOTAL":
                continue
            rows.append({"session": session, "who": who,
                         "fut_net": r["Future Index Long"] - r["Future Index Short"],
                         "call_net": r["Option Index Call Long"] - r["Option Index Call Short"],
                         "put_net": r["Option Index Put Long"] - r["Option Index Put Short"],
                         "call_short": r["Option Index Call Short"],
                         "put_short": r["Option Index Put Short"],
                         "fut_short": r["Future Index Short"]})
    return pd.DataFrame(rows)


def positions_before_expiry(poi: pd.DataFrame, moves: pd.DataFrame) -> pd.DataFrame:
    """Positions on the session before each index expiry, and their change on the expiry."""
    sessions = sorted(poi.session.unique(), key=lambda s: s[4:] + s[2:4] + s[:2])
    prev = {s: sessions[i - 1] for i, s in enumerate(sessions) if i}
    rows = []
    for _, m in moves[moves.expiry == 1].iterrows():
        if m.session not in prev:
            continue
        before = poi[poi.session == prev[m.session]].set_index("who")
        on = poi[poi.session == m.session].set_index("who")
        for who in before.index:
            rows.append({"session": m.session, "who": who, "rel_drift": m.rel_drift,
                         "monthly": m.monthly,
                         **{f"{c}_before": before.loc[who, c] for c in
                            ("fut_net", "call_net", "put_net", "call_short", "put_short")},
                         **{f"{c}_change": on.loc[who, c] - before.loc[who, c]
                            for c in ("fut_net", "call_net", "put_net")}})
    return pd.DataFrame(rows)


def position_regressions(pos: pd.DataFrame) -> pd.DataFrame:
    from scipy import stats
    rows = []
    for who, block in pos.groupby("who"):
        for x in ("fut_net_before", "fut_net_change", "call_net_before", "put_net_before"):
            sub = block.dropna(subset=[x, "rel_drift"])
            if len(sub) < 10 or sub[x].std() == 0:
                continue
            z = (sub[x] - sub[x].mean()) / sub[x].std()
            X = np.column_stack([np.ones(len(sub)), z])
            beta, *_ = np.linalg.lstsq(X, sub.rel_drift, rcond=None)
            resid = sub.rel_drift - X @ beta
            bread = np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(bread @ ((X * resid.to_numpy()[:, None] ** 2).T @ X) @ bread))
            rows.append({"who": who, "x": x, "n": len(sub), "slope_per_sd": beta[1],
                         "se": se[1],
                         "p": float(2 * stats.t.sf(abs(beta[1] / se[1]), len(sub) - 2))})
    return pd.DataFrame(rows)


def main() -> None:
    moves = index_moves()
    bhav = load_bhav()
    oi = expiring_oi(bhav, moves)
    oi.to_csv(RES / "s18_expiring_oi.csv", index=False)
    reg = oi_regressions(oi)
    reg.to_csv(RES / "s18_oi_regressions.csv", index=False)
    cash = cash_flow_tests()
    cash.to_csv(RES / "s18_cash_flows.csv", index=False)
    poi = participant_oi()
    pos = positions_before_expiry(poi, moves)
    pos.to_csv(RES / "s18_positions.csv", index=False)
    preg = position_regressions(pos)
    preg.to_csv(RES / "s18_position_regressions.csv", index=False)
    with pd.option_context("display.width", 200):
        print(pos.groupby("who")[["fut_net_before", "call_net_before", "put_net_before",
                                  "fut_net_change", "call_net_change",
                                  "put_net_change"]].median().round(0))
        print(preg.round(3).to_string(index=False))
    deriv = derivative_flows()
    deriv.to_csv(RES / "s18_index_deriv_flows.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(oi.describe().round(1).T[["count", "mean", "50%", "min", "max"]])
        print(reg.round(3).to_string(index=False))
        print(cash.round(3).to_string(index=False))
        if not deriv.empty:
            w = deriv[deriv.in_window & deriv.expiring]
            print(w.groupby(["kind", "is_expiry"])[["share_of_day", "net_aggressor", "prop_net",
                                                    "custodian_net"]].mean().round(1))


if __name__ == "__main__":
    main()
