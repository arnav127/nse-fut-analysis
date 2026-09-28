"""The settlement of the index, where the incentive is cash.

Stock derivatives were settled by delivery in 2022, which leaves a holder indifferent to the
settlement price (Section 7 of the paper). Index derivatives were not. Nifty 50 futures and
options are settled in cash against the index's closing value, which is computed from the
closing prices of its constituents - the settlement-window VWAPs. The index options expired
every Thursday, and they were by far the most traded derivatives on the exchange. If the
settlement window is pushed anywhere, it is here.

The exchange's index file gives, every second, the value of the Nifty 50 and of the Nifty
Next 50. The second index has no derivatives: it is the index-level placebo, exposed to the
same calendar and to the same market but to no settlement.

The closing value is not in the file; it is approximated by the average of the index over the
window. The index is a fixed-weight sum of prices, so its closing value is the same weighted
sum of the constituents' window VWAPs, which differs from the time average only through the
timing of each constituent's volume within the window.

Tests, on every session of the year:

  reversal   the next-morning return from the settlement value regressed on the window's move,
             with interactions for index expiries (every Thursday) and monthly expiries
  pinning    the distance of the settlement value to the nearest multiple of fifty, the
             strike interval of the weekly options, on expiry days and on other days
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config.settings import RAW_DATA_DIR, RESULTS_DIR  # noqa: E402
from stage9_tape.calendar import classify, next_session, trading_sessions  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.panel import fe_ols  # noqa: E402
from utils.paths import session_to_date  # noqa: E402

logger = setup_logger("IndexTests", "stage9_tape.log")

INDICES = {"nifty": (22, 30), "next50": (30, 38)}
STRIKE_STEP = {"nifty": 50.0, "next50": 50.0}
RI_DRAWS = 1000
SEED = 20220127

WINDOWS = {
    "open30": ("09:15:00", "09:45:00"),
    "pre10": ("14:50:00", "15:00:00"),
    "settle": ("15:00:00", "15:30:01"),
    "first1": ("15:00:00", "15:01:00"),
    "last1": ("15:29:00", "15:30:01"),
}


def read_index_file(session: str) -> Optional[pd.DataFrame]:
    path = Path(RAW_DATA_DIR) / f"CASH_Index_{session}.DAT.gz"
    if not path.exists():
        return None
    times, values = [], {k: [] for k in INDICES}
    with gzip.open(path, "rt", encoding="ascii", errors="replace") as handle:
        for line in handle:
            if not line.startswith("IX") or len(line.rstrip("\n")) < 38:
                continue
            times.append(line[14:22])
            for name, (a, b) in INDICES.items():
                values[name].append(int(line[a:b]) / 100.0)
    frame = pd.DataFrame({"time": times, **values})
    return frame[(frame.nifty > 0) & (frame.next50 > 0)]


def reduce_index(session: str) -> List[Dict]:
    frame = read_index_file(session)
    if frame is None or frame.empty:
        return []
    rows = []
    for name in INDICES:
        row = {"session": session, "index": name}
        for label, (lo, hi) in WINDOWS.items():
            part = frame[(frame.time >= lo) & (frame.time < hi)][name]
            row[label] = float(part.mean()) if len(part) else np.nan
        for k in range(6):
            lo = f"15:{5 * k:02d}:00"
            hi = f"15:{5 * (k + 1):02d}:00" if k < 5 else "15:30:01"
            part = frame[(frame.time >= lo) & (frame.time < hi)][name]
            row[f"w{k + 1}"] = float(part.mean()) if len(part) else np.nan
        row["last"] = float(frame[name].iloc[-1])
        rows.append(row)
    return rows


def build_index_panel() -> pd.DataFrame:
    sessions = trading_sessions()
    rows = []
    for session in sessions:
        try:
            rows.extend(reduce_index(session))
        except Exception as exc:  # a corrupt archive costs one day, not the year
            logger.error(f"[INDEX] {session}: {exc}")
    panel = pd.DataFrame(rows)
    kinds = classify(sessions)
    following = next_session(sessions)
    panel["day_type"] = panel.session.map(kinds)
    panel["date"] = panel.session.map(session_to_date)
    panel["month"] = panel.date.map(lambda d: d.month)
    panel["week"] = panel.date.map(lambda d: d.isocalendar()[:2]).astype(str)
    # Every Thursday expiry settles the index options; the monthly one also the futures.
    panel["expiry"] = panel.day_type.isin(["monthly_expiry", "weekly_expiry"]).astype(float)
    panel["monthly"] = (panel.day_type == "monthly_expiry").astype(float)
    panel["month_end"] = (panel.day_type == "month_end").astype(float)
    nxt = panel[["session", "index", "open30"]].rename(
        columns={"session": "next_session", "open30": "next_open30"})
    panel["next_session"] = panel.session.map(following)
    panel = panel.merge(nxt, on=["next_session", "index"], how="left")
    bps = 1e4
    panel["drift"] = bps * np.log(panel.settle / panel.pre10)
    panel["move"] = bps * np.log(panel.last1 / panel.first1)
    panel["next_rev"] = bps * np.log(panel.next_open30 / panel.settle)
    panel["next_rev_move"] = bps * np.log(panel.next_open30 / panel.last1)
    for base in ("drift", "move"):
        for flag in ("expiry", "monthly", "month_end"):
            panel[f"{base}_x_{flag}"] = panel[base] * panel[flag]
    step = panel["index"].map(STRIKE_STEP)
    for col in ("settle", "pre10"):
        value = panel[col] / step
        panel[f"dist_{col}"] = (value - np.round(value)).abs()
    panel["dist_change"] = panel.dist_settle - panel.dist_pre10
    return panel.sort_values(["index", "date"]).reset_index(drop=True)


def _spread(panel: pd.DataFrame) -> pd.DataFrame:
    """Nifty minus Nifty Next 50: removes the market move common to both indices."""
    wide = panel.pivot(index="session", columns="index")
    out = pd.DataFrame(index=wide.index)
    for col in ("drift", "move", "next_rev", "next_rev_move"):
        out[col] = wide[col]["nifty"] - wide[col]["next50"]
    for col in ("expiry", "monthly", "month_end", "day_type", "month", "week"):
        out[col] = wide[col]["nifty"]
    for base in ("drift", "move"):
        for flag in ("expiry", "monthly", "month_end"):
            out[f"{base}_x_{flag}"] = out[base] * out[flag]
    out["index"] = "spread"
    return out.reset_index()


def _pseudo(frame: pd.DataFrame, rng) -> pd.DataFrame:
    """Each expiry replaced by another session of the same week."""
    out = frame[frame.expiry == 0].copy()
    weeks = frame[frame.expiry == 1].week.unique()
    picks = []
    for week in weeks:
        pool = out[out.week == week].session.unique()
        if len(pool):
            picks.append(pool[rng.integers(len(pool))])
    out["expiry"] = out.session.isin(picks).astype(float)
    monthly_weeks = frame[frame.monthly == 1].week.unique()
    out["monthly"] = (out.session.isin(picks) & out.week.isin(monthly_weeks)).astype(float)
    for base in ("drift", "move"):
        for flag in ("expiry", "monthly"):
            out[f"{base}_x_{flag}"] = out[base] * out[flag]
    return out


def _fit(frame, y, x):
    return fe_ols(frame, y, x, fe=None, cluster="session")


def reversal_tests(panel: pd.DataFrame, ri: bool = True) -> pd.DataFrame:
    frames = {name: g for name, g in panel.groupby("index")}
    frames["spread"] = _spread(panel)
    rows = []
    specs = {
        "settlement": ("next_rev", "drift"),
        "window": ("next_rev_move", "move"),
    }
    for spec, (y, base) in specs.items():
        x = [base, f"{base}_x_expiry", f"{base}_x_monthly", f"{base}_x_month_end",
             "expiry", "monthly", "month_end"]
        for name, frame in frames.items():
            fit = _fit(frame, y, x)
            if fit is None:
                continue
            for term in (base, f"{base}_x_expiry", f"{base}_x_monthly"):
                row = {"spec": spec, "index": name, "term": term, "nobs": fit.nobs,
                       **fit.get(term)}
                if ri and term == f"{base}_x_expiry":
                    rng = np.random.default_rng(SEED)
                    draws = []
                    for _ in range(RI_DRAWS):
                        pf = _fit(_pseudo(frame, rng), y, x)
                        if pf is not None:
                            draws.append(pf.get(term)["coef"])
                    draws = np.asarray(draws)
                    row["ri_p"] = float(np.mean(np.abs(draws) >= abs(row["coef"])))
                rows.append(row)
    return pd.DataFrame(rows)


def activity_tests(panel: pd.DataFrame, ri: bool = True) -> pd.DataFrame:
    """Size of the window's move and of the final minutes on expiries, index by index."""
    frames = {name: g.copy() for name, g in panel.groupby("index")}
    spread = _spread(panel)
    frames["spread"] = spread
    rows = []
    for name, frame in frames.items():
        frame["abs_move"] = frame.move.abs()
        frame["abs_drift"] = frame.drift.abs()
        for y in ("abs_move", "abs_drift", "move", "drift", "next_rev"):
            x = ["expiry", "monthly", "month_end"]
            fit = _fit(frame, y, x)
            if fit is None:
                continue
            base = frame.loc[(frame.expiry == 0) & (frame.month_end == 0), y].mean()
            for term in ("expiry", "monthly"):
                row = {"index": name, "outcome": y, "term": term, "normal_mean": base,
                       "nobs": fit.nobs, **fit.get(term)}
                if ri and term == "expiry":
                    rng = np.random.default_rng(SEED)
                    draws = []
                    for _ in range(RI_DRAWS):
                        pseudo = _pseudo(frame, rng)
                        if y.startswith("abs_"):
                            pseudo[y] = pseudo[y.replace("abs_", "")].abs()
                        pf = _fit(pseudo, y, x)
                        if pf is not None:
                            draws.append(pf.get(term)["coef"])
                    draws = np.asarray(draws)
                    row["ri_p"] = float(np.mean(np.abs(draws) >= abs(row["coef"])))
                rows.append(row)
    return pd.DataFrame(rows)


def pinning_tests(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, frame in panel.groupby("index"):
        for y in ("dist_settle", "dist_change"):
            fit = _fit(frame, y, ["expiry"])
            if fit is None:
                continue
            base = frame.loc[frame.expiry == 0, y].mean()
            rows.append({"index": name, "outcome": y, "term": "expiry", "normal_mean": base,
                         "nobs": fit.nobs, **fit.get("expiry")})
    return pd.DataFrame(rows)


def run_index_tests(ri: bool = True) -> pd.DataFrame:
    panel = build_index_panel()
    out = Path(RESULTS_DIR)
    panel.to_csv(out / "s10_index_panel.csv", index=False)
    reversal = reversal_tests(panel, ri=ri)
    reversal.to_csv(out / "s10_index_reversal.csv", index=False)
    activity_tests(panel, ri=ri).to_csv(out / "s10_index_activity.csv", index=False)
    pinning_tests(panel).to_csv(out / "s10_index_pinning.csv", index=False)
    logger.info(f"[S10] index tests on {panel.session.nunique()} sessions")
    return reversal


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ri", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 200)
    print(run_index_tests(ri=not args.no_ri).round(3).to_string(index=False))
