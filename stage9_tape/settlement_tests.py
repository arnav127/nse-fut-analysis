"""Is the settlement price pushed? Tests on the full-year tape.

Three questions, each answered by comparing the monthly expiry with every other session of
the year rather than with a single control.

**Is the window abnormal?** Window volume share, the distance of the settlement VWAP from
the price before the window, and the distance of the final five minutes from the settlement
price, regressed on day-type indicators with security fixed effects. The weekly index expiry
and the month end are the calendar controls: each shares one feature of the monthly expiry
and not the stock derivatives settlement.

**Does the settlement price reverse?** A price pushed to a level that the flow cannot hold
returns once the flow stops. The window closes the session, so the test is on the next
morning: the return from the settlement price to the next session's opening half-hour VWAP,
regressed on the window's own move. Some reversal is expected on any day - a move produced
by liquidity demand partly reverts - so the quantity of interest is the additional reversal
on monthly expiries, and whether it is confined to securities with an expiring contract.
This is the signature that the literature on closing-price manipulation uses (Carhart et al.
2002; Hillion and Suominen 2004; Comerton-Forde and Putnins 2011).

**Whose flow moves it?** The window's move regressed on net aggressor-signed volume, split
by participant category, and the next-morning return on the same flows. Flow that moves the
settlement price and is then reversed is flow that pushed the price rather than informed it.

Inference is clustered by session. With twelve monthly expiries, a cluster-robust standard
error on a monthly-expiry coefficient rests on few clusters, so every headline coefficient is
also compared with its randomization distribution: the same regression with the twelve
expiries replaced by one ordinary session drawn at random from each month.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config.settings import RESULTS_DIR  # noqa: E402
from config.universe import GROUPS, group_of  # noqa: E402
from stage9_tape.calendar import DAY_TYPES, classify, next_session, trading_sessions  # noqa: E402
from stage9_tape.daily_tape import PARTICIPANTS, load_tape  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.panel import fe_ols, winsorize  # noqa: E402
from utils.paths import session_to_date  # noqa: E402

logger = setup_logger("SettlementTests", "stage9_tape.log")

EVENT_TYPES = [t for t in DAY_TYPES if t != "normal"]
DERIVATIVE_GROUPS = ("liquid", "illiquid")
GROUP_SETS = {"liquid": ["liquid"], "illiquid": ["illiquid"], "placebo": ["placebo"],
              "derivative": list(DERIVATIVE_GROUPS)}

RI_DRAWS = 1000

# Security and session effects. The session effect removes market-wide moves, which on a
# handful of expiry days would otherwise dominate every return-based estimate.
TWO_WAY = ("symbol", "session")
SEED = 20220127

ACTIVITY_MEASURES = {
    "window_share": "Share of the session's volume traded in the window (pp)",
    "abs_drift": "|Settlement VWAP vs pre-window VWAP| (bps)",
    "abs_terminal": "|Final five minutes vs settlement VWAP| (bps)",
}


def build_panel(tape: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    tape = load_tape() if tape is None else tape
    if tape.empty:
        return tape
    # The calendar comes from the exchange's file list, not from the sessions that reduced
    # successfully. A session whose file could not be read is still a trading day: the
    # session before it has no next morning in the panel, rather than taking the one after.
    calendar = sorted(set(trading_sessions()) | set(tape.session), key=session_to_date)
    kinds = classify(calendar)
    following = next_session(calendar)

    panel = tape.copy()
    panel["group"] = panel.symbol.map(group_of)
    panel = panel[panel.group.isin(GROUPS.keys())].copy()
    panel["day_type"] = panel.session.map(kinds)
    panel["date"] = panel.session.map(session_to_date)
    panel["month"] = panel.date.map(lambda d: d.month)
    panel["derivative"] = panel.group.isin(DERIVATIVE_GROUPS).astype(float)
    for t in EVENT_TYPES:
        panel[t] = (panel.day_type == t).astype(float)

    nxt = panel[["symbol", "session", "open30_vwap"]].rename(
        columns={"session": "next_session", "open30_vwap": "next_open30_vwap"})
    panel["next_session"] = panel.session.map(following)
    panel = panel.merge(nxt, on=["symbol", "next_session"], how="left")

    reference = panel.pre10_vwap.fillna(panel.pre_last)
    bps = 1e4
    panel["drift"] = bps * np.log(panel.settle_vwap / reference)
    panel["next_rev"] = bps * np.log(panel.next_open30_vwap / panel.settle_vwap)
    panel["terminal"] = bps * np.log(panel.last5_vwap / panel.settle_vwap)
    panel["abs_drift"] = panel.drift.abs()
    panel["abs_terminal"] = panel.terminal.abs()
    panel["window_share"] = 100.0 * panel.window_volume / panel.volume

    # Flow in per cent of the security's median session volume, so that a coefficient is
    # comparable across securities whose volume differs by orders of magnitude.
    adv = panel.groupby("symbol").volume.transform("median")
    panel["flow"] = 100.0 * panel.window_signed / adv
    for name in PARTICIPANTS.values():
        panel[f"flow_{name}"] = 100.0 * panel[f"window_signed_{name}"].fillna(0.0) / adv
        panel[f"share_{name}"] = (100.0 * panel[f"window_volume_{name}"].fillna(0.0)
                                  / (2.0 * panel.window_volume))

    # Corporate actions put the next morning's open on a different basis from the
    # settlement price, and a handful of such days would dominate any regression on returns.
    # Winsorized within group at one per cent in each tail.
    for column in ("drift", "next_rev", "terminal", "abs_drift", "abs_terminal", "flow",
                   *[f"flow_{n}" for n in PARTICIPANTS.values()]):
        panel[column] = panel.groupby("group")[column].transform(winsorize)
    for t in EVENT_TYPES:
        panel[f"drift_x_{t}"] = panel.drift * panel[t]
        panel[f"flow_x_{t}"] = panel.flow * panel[t]
        for name in PARTICIPANTS.values():
            panel[f"flow_{name}_x_{t}"] = panel[f"flow_{name}"] * panel[t]

    # Order imbalance, (BI - SI) / (BI + SI), over the whole window and in each five-minute
    # block, and the move from the window's first minute to its last.
    if "w1_bi" in panel.columns:
        bi = sum(panel[f"w{k}_bi"].fillna(0.0) for k in range(1, 7))
        si = sum(panel[f"w{k}_si"].fillna(0.0) for k in range(1, 7))
        panel["oib"] = (bi - si) / (bi + si).replace(0, np.nan)
        panel["abs_oib"] = panel.oib.abs()
        for k in range(1, 7):
            b, s_ = panel[f"w{k}_bi"].fillna(0.0), panel[f"w{k}_si"].fillna(0.0)
            panel[f"oib{k}"] = (b - s_) / (b + s_).replace(0, np.nan)
        panel["move1530"] = bps * np.log(panel.last1_vwap / panel.first1_vwap)
        panel["move1530"] = panel.groupby("group")["move1530"].transform(winsorize)
        panel["abs_move1530"] = panel.move1530.abs()
        # Thursday expiries of either kind settle the index options.
        panel["index_expiry"] = panel.day_type.isin(["monthly_expiry", "weekly_expiry"]
                                                    ).astype(float)
        for t in EVENT_TYPES:
            panel[f"oib_x_{t}"] = panel.oib * panel[t]
    return panel


def _subset(panel: pd.DataFrame, key: str) -> pd.DataFrame:
    return panel[panel.group.isin(GROUP_SETS[key])]


# --- models ---------------------------------------------------------------------------

def _activity(frame: pd.DataFrame, measure: str, event: str = "monthly_expiry"):
    return fe_ols(frame, measure, EVENT_TYPES), event


def _reversal_x() -> List[str]:
    return ["drift", *[f"drift_x_{t}" for t in EVENT_TYPES], *EVENT_TYPES]


def _flow_x() -> List[str]:
    return ["flow", *[f"flow_x_{t}" for t in EVENT_TYPES], *EVENT_TYPES]


def _participant_x() -> List[str]:
    names = list(PARTICIPANTS.values())
    return ([f"flow_{n}" for n in names]
            + [f"flow_{n}_x_monthly_expiry" for n in names]
            + [f"flow_{n}_x_{t}" for n in names for t in EVENT_TYPES if t != "monthly_expiry"]
            + EVENT_TYPES)


def _did_frame(panel: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Derivative groups against the placebo group: every regressor also interacted."""
    frame = panel[panel.group.isin([*DERIVATIVE_GROUPS, "placebo"])].copy()
    for c in columns:
        frame[f"{c}_x_deriv"] = frame[c] * frame.derivative
    return frame


# --- randomization inference ------------------------------------------------------------

def _pseudo_panel(panel: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Replace the twelve expiries by one ordinary session drawn from each month."""
    frame = panel[panel.day_type != "monthly_expiry"].copy()
    normal = frame[frame.day_type == "normal"][["session", "month"]].drop_duplicates()
    picks = normal.groupby("month").session.apply(
        lambda s: s.iloc[rng.integers(len(s))]).tolist()
    frame["monthly_expiry"] = frame.session.isin(picks).astype(float)
    frame.loc[frame.monthly_expiry > 0, "day_type"] = "monthly_expiry"
    frame["drift_x_monthly_expiry"] = frame.drift * frame.monthly_expiry
    frame["flow_x_monthly_expiry"] = frame.flow * frame.monthly_expiry
    for name in PARTICIPANTS.values():
        frame[f"flow_{name}_x_monthly_expiry"] = frame[f"flow_{name}"] * frame.monthly_expiry
    return frame


def randomization_p(panel: pd.DataFrame, y: str, x: List[str], target: str,
                    observed: float, did: bool = False, draws: int = RI_DRAWS,
                    fe=TWO_WAY) -> Dict[str, float]:
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(draws):
        pseudo = _pseudo_panel(panel, rng)
        frame = _did_frame(pseudo, x) if did else pseudo
        cols = x + ([f"{c}_x_deriv" for c in x] if did else [])
        fit = fe_ols(frame, y, cols, fe=fe)
        if fit is not None and target in fit.names:
            values.append(fit.get(target)["coef"])
    values = np.asarray(values)
    if values.size == 0 or not np.isfinite(observed):
        return {"ri_p": np.nan, "ri_draws": 0}
    return {"ri_p": float(np.mean(np.abs(values) >= abs(observed))),
            "ri_draws": int(values.size),
            "ri_sd": float(values.std(ddof=1))}


# --- the three tables ------------------------------------------------------------------

PRESSURE_MEASURES = {
    "abs_oib": "|Order imbalance| over the window",
    "oib": "Order imbalance over the window",
    "move1530": "Move from 15:00 to 15:30 (bps)",
    "abs_move1530": "|Move from 15:00 to 15:30| (bps)",
}


def pressure_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Order imbalance on each type of session: is the window more one-sided on expiry?"""
    if "oib" not in panel.columns:
        return pd.DataFrame()
    return activity_table(panel, PRESSURE_MEASURES)


def oib_dynamics(panel: pd.DataFrame) -> pd.DataFrame:
    """Persistence of imbalance across the window's blocks, and its effect on the price.

    Persistence: the imbalance of each five-minute block regressed on that of the block
    before, with interactions for the session types. One-sided pressure sustained through the
    window shows as higher persistence. Price effect: the move from 15:00 to 15:30 regressed
    on the window's imbalance, with security and session effects.
    """
    if "oib" not in panel.columns:
        return pd.DataFrame()
    rows = []
    blocks = []
    for k in range(2, 7):
        part = panel[["symbol", "session", "group", *EVENT_TYPES]].copy()
        part["y"] = panel[f"oib{k}"]
        part["lag"] = panel[f"oib{k - 1}"]
        blocks.append(part)
    long = pd.concat(blocks, ignore_index=True)
    for t in EVENT_TYPES:
        long[f"lag_x_{t}"] = long.lag * long[t]
    x = ["lag", *[f"lag_x_{t}" for t in EVENT_TYPES], *EVENT_TYPES]
    for key in GROUP_SETS:
        fit = fe_ols(long[long.group.isin(GROUP_SETS[key])], "y", x, fe="symbol")
        if fit is None:
            continue
        for term in ("lag", "lag_x_monthly_expiry", "lag_x_weekly_expiry"):
            rows.append({"model": "persistence", "sample": key, "term": term,
                         "nobs": fit.nobs, "sessions": fit.clusters, **fit.get(term)})
    # Against the placebo group: every regressor also interacted with the treated group.
    for label, treated in (("did", list(DERIVATIVE_GROUPS)), ("did_liquid", ["liquid"])):
        frame = long[long.group.isin([*treated, "placebo"])].copy()
        frame["treat"] = frame.group.isin(treated).astype(float)
        cols = list(x)
        for c in x:
            frame[f"{c}_x_treat"] = frame[c] * frame.treat
            cols.append(f"{c}_x_treat")
        fit = fe_ols(frame, "y", cols, fe="symbol")
        if fit is None:
            continue
        for term in ("lag", "lag_x_monthly_expiry", "lag_x_weekly_expiry"):
            rows.append({"model": "persistence", "sample": label, "term": term,
                         "nobs": fit.nobs, "sessions": fit.clusters,
                         **fit.get(f"{term}_x_treat")})
    x = ["oib", *[f"oib_x_{t}" for t in EVENT_TYPES]]
    for key in GROUP_SETS:
        fit = fe_ols(_subset(panel, key), "move1530", x, fe=TWO_WAY)
        if fit is None:
            continue
        for term in ("oib", "oib_x_monthly_expiry", "oib_x_weekly_expiry"):
            rows.append({"model": "price", "sample": key, "term": term,
                         "nobs": fit.nobs, "sessions": fit.clusters, **fit.get(term)})
    return pd.DataFrame(rows)


def index_channel(panel: pd.DataFrame) -> pd.DataFrame:
    """Signed window move of each derivatives group against the placebo on index expiries.

    The index options settle in cash on every Thursday expiry. The liquid group consists
    largely of index constituents and the illiquid group largely of securities outside the
    index, so an effect that runs through the index settlement should appear in the first
    and not the second.
    """
    if "index_expiry" not in panel.columns:
        return pd.DataFrame()
    rows = []
    for group in DERIVATIVE_GROUPS:
        frame = panel[panel.group.isin([group, "placebo"])].copy()
        frame["treat"] = (frame.group == group).astype(float)
        frame["ie_x_t"] = frame.index_expiry * frame.treat
        frame["me_x_t"] = frame.monthly_expiry * frame.treat
        frame["end_x_t"] = frame.month_end * frame.treat
        for y in ("drift", "move1530", "next_rev"):
            fit = fe_ols(frame, y, ["ie_x_t", "me_x_t", "end_x_t"], fe=TWO_WAY)
            if fit is None:
                continue
            for term, label in (("ie_x_t", "index_expiry"), ("me_x_t", "monthly_extra")):
                rows.append({"group": group, "outcome": y, "term": label, "nobs": fit.nobs,
                             "sessions": fit.clusters, **fit.get(term)})
    return pd.DataFrame(rows)


def activity_table(panel: pd.DataFrame, measures: Optional[Dict[str, str]] = None
                   ) -> pd.DataFrame:
    rows = []
    for measure, label in (measures or ACTIVITY_MEASURES).items():
        for key in GROUP_SETS:
            frame = _subset(panel, key)
            fit = fe_ols(frame, measure, EVENT_TYPES)
            if fit is None:
                continue
            base = frame.loc[frame.day_type == "normal", measure].mean()
            for t in EVENT_TYPES:
                rows.append({"measure": measure, "label": label, "sample": key, "term": t,
                             "normal_mean": base, "nobs": fit.nobs, "sessions": fit.clusters,
                             **fit.get(t)})
        did = _did_frame(panel, EVENT_TYPES)
        fit = fe_ols(did, measure, [f"{t}_x_deriv" for t in EVENT_TYPES], fe=TWO_WAY)
        if fit is not None:
            for t in EVENT_TYPES:
                rows.append({"measure": measure, "label": label, "sample": "did", "term": t,
                             "nobs": fit.nobs, "sessions": fit.clusters,
                             **fit.get(f"{t}_x_deriv")})
    return pd.DataFrame(rows)


def reversal_table(panel: pd.DataFrame, ri: bool = True) -> pd.DataFrame:
    x = _reversal_x()
    rows = []
    for key in GROUP_SETS:
        frame = _subset(panel, key)
        fit = fe_ols(frame, "next_rev", x, fe=TWO_WAY)
        if fit is None:
            continue
        for term in ["drift", *[f"drift_x_{t}" for t in EVENT_TYPES]]:
            row = {"sample": key, "term": term, "nobs": fit.nobs, "sessions": fit.clusters,
                   **fit.get(term)}
            if ri and term == "drift_x_monthly_expiry":
                row.update(randomization_p(frame, "next_rev", x, term, row["coef"]))
            rows.append(row)
    did = _did_frame(panel, x)
    cols = x + [f"{c}_x_deriv" for c in x]
    fit = fe_ols(did, "next_rev", cols, fe=TWO_WAY)
    if fit is not None:
        for term in ["drift", *[f"drift_x_{t}" for t in EVENT_TYPES]]:
            row = {"sample": "did", "term": term, "nobs": fit.nobs, "sessions": fit.clusters,
                   **fit.get(f"{term}_x_deriv")}
            if ri and term == "drift_x_monthly_expiry":
                row.update(randomization_p(panel, "next_rev", x, f"{term}_x_deriv",
                                           row["coef"], did=True))
            rows.append(row)
    return pd.DataFrame(rows)


def flow_table(panel: pd.DataFrame, ri: bool = True) -> pd.DataFrame:
    """Price impact of window flow, and how much of it is reversed the next morning."""
    rows = []
    for outcome in ("drift", "next_rev"):
        for model, x in (("all", _flow_x()), ("participant", _participant_x())):
            for key in GROUP_SETS:
                frame = _subset(panel, key)
                fit = fe_ols(frame, outcome, x, fe=TWO_WAY)
                if fit is None:
                    continue
                terms = ([c for c in x if c.startswith("flow") and
                          (c.endswith("monthly_expiry") or "_x_" not in c)])
                for term in terms:
                    row = {"outcome": outcome, "model": model, "sample": key, "term": term,
                           "nobs": fit.nobs, "sessions": fit.clusters, **fit.get(term)}
                    if (ri and model == "all" and term == "flow_x_monthly_expiry"
                            and key in ("derivative", "placebo")):
                        row.update(randomization_p(frame, outcome, x, term, row["coef"]))
                    rows.append(row)
    return pd.DataFrame(rows)


def day_type_profile(panel: pd.DataFrame) -> pd.DataFrame:
    """Means by day type and group, for the descriptive table and the figure."""
    columns = ["window_share", "abs_drift", "abs_terminal", "next_rev", "drift",
               *[f"share_{n}" for n in PARTICIPANTS.values()]]
    frame = panel.groupby(["group", "day_type"])[columns].mean().reset_index()
    counts = panel.groupby(["group", "day_type"]).agg(
        observations=("symbol", "size"), sessions=("session", "nunique")).reset_index()
    return frame.merge(counts, on=["group", "day_type"])


def window_path(panel: pd.DataFrame) -> pd.DataFrame:
    """Average signed path through the window, oriented by the direction of the move.

    Each security-session's five-minute VWAPs relative to the pre-window VWAP, multiplied by
    the sign of the window's move, then the next morning. Oriented this way a push and its
    release show as a rise and a fall whatever the direction of the push.
    """
    # Each point is measured relative to the same point's average across the universe on
    # that session, so that a market-wide move does not appear as a push and its release.
    reference = panel.pre10_vwap.fillna(panel.pre_last)
    raw = {f"w{k}": 1e4 * np.log(panel[f"w{k}_vwap"] / reference) for k in range(1, 7)}
    raw["settle"] = panel.drift
    raw["next_open"] = panel.drift + panel.next_rev
    adjusted = {k: v - v.groupby(panel.session).transform("mean") for k, v in raw.items()}
    sign = np.sign(adjusted["settle"])
    points = {"pre": pd.Series(0.0, index=panel.index)}
    for k, v in adjusted.items():
        points[k] = v * sign
    frame = pd.DataFrame(points)
    frame["group"] = panel.group.values
    frame["day_type"] = panel.day_type.values
    frame = frame.replace([np.inf, -np.inf], np.nan)
    long = frame.melt(id_vars=["group", "day_type"], var_name="point", value_name="bps")
    return (long.groupby(["group", "day_type", "point"]).bps
            .agg(["mean", "sem", "count"]).reset_index())


def figure_summaries(panel: pd.DataFrame) -> None:
    """Small tables the report's figures are drawn from.

    The panel itself stays on the machine that holds the data; these carry only group means,
    so the figures can be rebuilt wherever the document is typeset.
    """
    out = Path(RESULTS_DIR)
    daily = (panel.groupby(["session", "group", "day_type"])
             .agg(window_share=("window_share", "mean"), abs_drift=("abs_drift", "mean"))
             .reset_index())
    daily["date"] = daily.session.map(lambda x: session_to_date(x).isoformat())
    daily.to_csv(out / "s9_daily.csv", index=False)
    if "oib1" in panel.columns:
        rows = []
        for (group, kind), block in panel.groupby(["group", "day_type"]):
            for k in range(1, 7):
                values = block[f"oib{k}"]
                rows.append({"group": group, "day_type": kind, "block": k,
                             "oib": float(values.mean()),
                             "abs_oib": float(values.abs().mean()),
                             "sem": float(values.abs().sem())})
        pd.DataFrame(rows).to_csv(out / "s9_oib_path.csv", index=False)


def run_settlement_tests(ri: bool = True) -> pd.DataFrame:
    panel = build_panel()
    if panel.empty:
        logger.warning("[S9] no tape; run stage9_tape.daily_tape first")
        return panel
    out = Path(RESULTS_DIR)
    logger.info(f"[S9] panel: {len(panel):,} security-sessions, "
                f"{panel.session.nunique()} sessions, {panel.symbol.nunique()} securities")
    panel.to_parquet(out / "s9_panel.parquet", index=False)
    day_type_profile(panel).to_csv(out / "s9_day_type_profile.csv", index=False)
    window_path(panel).to_csv(out / "s9_window_path.csv", index=False)
    activity = activity_table(panel)
    activity.to_csv(out / "s9_activity.csv", index=False)
    reversal = reversal_table(panel, ri=ri)
    reversal.to_csv(out / "s9_reversal.csv", index=False)
    flow = flow_table(panel, ri=ri)
    flow.to_csv(out / "s9_flow.csv", index=False)
    pressure_table(panel).to_csv(out / "s9_pressure.csv", index=False)
    oib_dynamics(panel).to_csv(out / "s9_oib_dynamics.csv", index=False)
    index_channel(panel).to_csv(out / "s9_index_channel.csv", index=False)
    figure_summaries(panel)
    logger.info("[S9] settlement tests written")
    return reversal


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ri", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 200)
    print(run_settlement_tests(ri=not args.no_ri).to_string(index=False))
