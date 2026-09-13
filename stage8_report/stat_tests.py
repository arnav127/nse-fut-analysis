"""Paired hypothesis testing for H1-H30, with multiplicity control.

Every hypothesis has the same shape: a per-symbol quantity measured on an expiry Thursday
against the same quantity on that month's matched control day. So each one reduces to a
paired test over symbol-session pairs, and the only thing that varies is which results file
and column the quantity comes from.

Two things this had to be corrected on.

*Pairing was many-to-many.* The expiry and control rows were merged on `symbol` alone, but
most results files carry several rows per symbol per session - broken out by minute bucket,
participant class, algo class or side. Merging on symbol alone formed the cross product of
those rows, so a 15:03 custodian-algo bucket was paired with a 15:27 proprietary-manual one
and counted as a matched observation. On the cancellation file that is up to 360 rows a side,
or roughly 130,000 spurious pairs per symbol-month. Every quantity is now reduced to one
value per symbol and session before anything is paired.

*The FDR step-up was not a step-up.* Benjamini-Hochberg finds the largest rank k whose
p-value clears k/n times alpha and rejects everything up to that rank. Testing each rank
against its own threshold independently, as this did, can reject a hypothesis while leaving
a smaller p-value un-rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from config.settings import EXPIRY_CONTROL_PAIRS, RESULTS_DIR

ALPHA = 0.05

@dataclass(frozen=True)
class Hypothesis:
    """One hypothesis and how to measure it.

    `direction` is what the hypothesis claims: "+" for higher on expiry, "-" for lower,
    "two" when the statement is only that the quantity differs. It exists because a paired
    t-test is two-sided, so a small p-value says the quantity moved, not that it moved the
    way the hypothesis said. Three of these turn out to move the other way, and without the
    stated direction recorded the paper would report them as confirmations.

    `reduce` matters too: a count summed and a rate averaged are different quantities, and
    the mean of a count across minute buckets answers a different question from the total.
    `row_filter` narrows the rows for a hypothesis stated about part of the window.
    """

    hid: str
    description: str
    source: str
    column: str
    reduce: str
    direction: str = "+"
    row_filter: Optional[Tuple[str, Any]] = None


H = Hypothesis

# The set is organised by what each question is about, not by which file answers it.
#
# Six of the original thirty are gone. H10 (aggressive order share) restated H6 and H11 on a
# combined column; H25 (Herfindahl of volume across the window) and H29 (Gini of the same
# series) are two names for one measure, and the Gini is kept; H19 (book pressure magnitude)
# overlapped H15 and H18; H4 asked only whether custodian counts "shift", which no direction
# and no mechanism made falsifiable; H2 and H13 were stated as moderation claims - worse for
# illiquid securities - but tested as ordinary paired differences on an unrelated column,
# and moderation is now tested properly in Table 4 rather than pretended at here.
#
# What replaces them measures the settlement price itself, which the original design never
# computed, and separates directional pressure from ordinary congestion, which it could not.
HYPOTHESES: List[Hypothesis] = [
    # --- the settlement price -------------------------------------------------------
    H("S1", "Settlement VWAP sits further from the window's opening mid",
      "s1_settlement_price.csv", "abs_drift_bps", "mean"),
    H("S2", "Settlement VWAP sits further from the closing price",
      "s1_settlement_price.csv", "abs_reversal_bps", "mean"),
    H("S3", "The final minute's VWAP diverges further from the window's",
      "s1_settlement_price.csv", "terminal_gap_bps", "mean"),
    H("S4", "Less volume transacts at the running VWAP",
      "s1_settlement_price.csv", "vwap_tracking_share", "mean", "-"),
    H("S5", "Volume concentrates into the final minute",
      "s1_settlement_price.csv", "final_minute_volume_share", "mean"),

    # --- pressure or activity -------------------------------------------------------
    H("P1", "Prices trend rather than oscillate (variance ratio rises)",
      "s2_pressure_or_activity.csv", "variance_ratio", "mean"),
    H("P2", "Signed order flow is more persistent",
      "s2_pressure_or_activity.csv", "flow_autocorr", "mean"),
    H("P3", "A larger share of price impact is permanent",
      "s2_pressure_or_activity.csv", "permanent_share", "mean"),
    H("P4", "Flow of a given size moves the price further",
      "s2_pressure_or_activity.csv", "impact_short_bps", "mean"),

    # --- concealment ----------------------------------------------------------------
    H("C1", "More resting size is concealed",
      "s3_hidden_liquidity.csv", "concealed_depth_share", "mean"),
    H("C2", "Concealed parent orders are larger relative to displayed ones",
      "s3_hidden_liquidity.csv", "concealed_size_multiple", "mean"),
    H("C3", "Concealed size is replenished more per unit matched",
      "s3_hidden_liquidity.csv", "replenishment_rate", "mean"),
    H("C4", "A greater share of submitted volume is concealed",
      "s3_hidden_liquidity.csv", "concealed_volume_share", "mean"),

    # --- the cost of moving the book ------------------------------------------------
    H("M1", "A fixed order moves the price further",
      "s4_marking_cost.csv", "move_bps_0p1", "mean"),
    H("M2", "Displayed notional in the book falls",
      "s4_marking_cost.csv", "visible_notional_cr", "mean", "-"),

    # --- liquidity supply (retained from the original design) -----------------------
    H("H12", "Bid-ask spread widens on expiry",
      "b1_spread_dynamics.csv", "mean_spread_bps", "mean"),
    H("H14", "Order book depth erodes on expiry",
      "b2_depth_erosion.csv", "avg_bid_depth", "mean", "-"),
    H("H15", "Depth erosion is asymmetric",
      "b2_depth_erosion.csv", "abs_imbalance", "mean"),
    H("H17", "Price impact per trade is higher",
      "b4_price_impact.csv", "median_price_impact_bps", "mean"),
    H("H18", "Book pressure is more persistent",
      "b5_book_asymmetry.csv", "book_pressure_persistence", "mean"),
    H("H30", "Post-shock spread recovery time differs",
      "b7_market_resilience.csv", "mean_recovery_time_sec", "mean", "two"),

    # --- order behaviour (retained) --------------------------------------------------
    H("H3", "Proprietary desks take a larger share of volume",
      "a3_participant_profile.csv", "volume", "sum"),
    H("H5", "Algorithmic flow takes a larger share of volume",
      "a4_algo_segmentation.csv", "total_volume", "sum"),
    H("H6", "Algorithmic orders carry immediate-or-cancel more often",
      "a4_algo_segmentation.csv", "ioc_rate", "mean"),
    H("H7", "Cancellations per entry rise",
      "a5_cancellation_patterns.csv", "cancel_to_entry_ratio", "mean"),
    H("H8", "Cancellation counts rise",
      "a5_cancellation_patterns.csv", "cancellations", "sum"),
    H("H9", "More entered orders carry a disclosed quantity below their total",
      "a6_iceberg_detection.csv", "iceberg_ratio", "mean"),
    H("H11", "Immediate-or-cancel submission accelerates in the final five minutes",
      "a7_ioc_aggressiveness.csv", "ioc_ratio", "mean", "+", ("sub_window", "Late")),
    H("H16", "Submitted order flow is more one-sided",
      "b3_order_flow_imbalance.csv", "cash_ofi", "mean"),
    H("H28", "More orders are cancelled within one second of entry",
      "a12_order_lifespan.csv", "phantom_order_rate", "mean"),
    H("H29", "Traded volume is less evenly spread across the window",
      "b6_volume_profile.csv", "volume_gini", "mean"),

    # --- regime (retained) -----------------------------------------------------------
    H("H24", "Realised variance per minute is higher",
      "a8_volatility_regime.csv", "rv_ratio", "mean"),
    H("H27", "Amihud illiquidity is higher relative to the rest of the session",
      "a11_amihud_illiquidity.csv", "amihud_uplift", "mean"),
]

# Questions the design specifies but this data cannot answer. Listed rather than dropped:
# a reader is entitled to know what was asked and left open, and a hypothesis that silently
# disappears between the design and the results is the one worth asking about.
OUT_OF_SCOPE: List[tuple] = [
    ("X1", "Cash-futures basis volatility is higher on expiry",
     "requires the FAO feed; no futures files are held"),
    ("X2", "Futures returns lead cash returns within the window",
     "requires the FAO feed; no futures files are held"),
    ("X3", "VWAP drift aligns with the direction of roll pressure",
     "requires open-interest and calendar-spread data from a terminal"),
    ("X4", "Basis mispricing scales with roll intensity",
     "requires cost-of-carry data from a terminal"),
]


def _session_level(
    df: pd.DataFrame,
    column: str,
    how: str,
    row_filter: Optional[Tuple[str, Any]] = None,
) -> pd.DataFrame:
    """Reduce a results file to one value per symbol and session.

    Every results file is keyed by at least (symbol, trade_date); the finer breakdowns are
    what a paired symbol-session test has to collapse before it can pair anything.
    """
    if row_filter is not None:
        filter_column, value = row_filter
        if filter_column not in df.columns:
            return df.iloc[0:0]
        df = df[df[filter_column] == value]
    frame = df[["symbol", "trade_date", column]].copy()
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=[column])
    if frame.empty:
        return frame
    return frame.groupby(["symbol", "trade_date"], as_index=False)[column].agg(how)


def _consistent(direction: str, effect: float) -> bool:
    """Does the observed effect point the way the hypothesis said it would?"""
    if direction == "two":
        return True
    return effect > 0 if direction == "+" else effect < 0


def _evaluate(h: Hypothesis) -> Optional[Dict[str, Any]]:
    h_id, desc, file_name, column, how = h.hid, h.description, h.source, h.column, h.reduce
    row_filter = h.row_filter
    path = Path(RESULTS_DIR) / file_name
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or column not in df.columns or "trade_date" not in df.columns:
        return None

    reduced = _session_level(df, column, how, row_filter)
    if reduced.empty:
        return None

    # Session is derived here rather than stored, so the calendar - which is written the way
    # NSE names its files - can be matched against an ISO trade_date.
    reduced["session"] = pd.to_datetime(reduced["trade_date"], errors="coerce").dt.strftime("%d%m%Y")
    by_session = {s: g.set_index("symbol")[column] for s, g in reduced.groupby("session")}

    expiry_vals: List[float] = []
    control_vals: List[float] = []
    months = 0
    for expiry_session, control_session in EXPIRY_CONTROL_PAIRS:
        exp = by_session.get(expiry_session)
        ctl = by_session.get(control_session)
        if exp is None or ctl is None:
            continue
        # Intersecting the two indexes pairs each symbol with itself and nothing else.
        common = exp.index.intersection(ctl.index)
        if common.empty:
            continue
        months += 1
        expiry_vals.extend(exp.loc[common].to_numpy())
        control_vals.extend(ctl.loc[common].to_numpy())

    exp_arr = np.asarray(expiry_vals, dtype=np.float64)
    ctl_arr = np.asarray(control_vals, dtype=np.float64)
    finite = np.isfinite(exp_arr) & np.isfinite(ctl_arr)
    exp_arr, ctl_arr = exp_arr[finite], ctl_arr[finite]

    if exp_arr.size < 2:
        return None

    diffs = exp_arr - ctl_arr
    sd = float(np.std(diffs, ddof=1))
    if sd == 0:
        # Identical on every pair. A t statistic is undefined here, and reporting p = 0
        # would be the strongest result in the table for a variable that never moved.
        return {
            "hypothesis_id": h_id, "description": desc, "test_name": "Paired t-test",
            "test_stat": np.nan, "p_value": np.nan, "effect_size_cohen_d": 0.0,
            "n_pairs": int(exp_arr.size), "n_months": months,
            "mean_expiry": float(exp_arr.mean()), "mean_control": float(ctl_arr.mean()),
            "stated_direction": h.direction, "direction_consistent": True,
            "note": "no variation in paired differences",
        }

    t_stat, p_val = stats.ttest_rel(exp_arr, ctl_arr)
    # Wilcoxon alongside the t-test: these distributions are heavy-tailed and the sample is
    # a few hundred pairs, so a result that holds under both is worth distinguishing from
    # one that depends on the normality assumption.
    try:
        _, w_p = stats.wilcoxon(exp_arr, ctl_arr)
    except ValueError:
        w_p = np.nan

    return {
        "hypothesis_id": h_id,
        "description": desc,
        "test_name": "Paired t-test",
        "test_stat": float(t_stat),
        "p_value": float(p_val),
        "wilcoxon_p_value": float(w_p) if np.isfinite(w_p) else np.nan,
        "effect_size_cohen_d": float(diffs.mean() / sd),
        "n_pairs": int(exp_arr.size),
        "n_months": months,
        "mean_expiry": float(exp_arr.mean()),
        "mean_control": float(ctl_arr.mean()),
        "stated_direction": h.direction,
        "direction_consistent": _consistent(h.direction, float(diffs.mean())),
        "note": "",
    }


def _benjamini_hochberg(p_values: np.ndarray, alpha: float) -> np.ndarray:
    """Step-up FDR control: reject ranks 1..k for the largest k with p_(k) <= k/n * alpha.

    The step-up is the whole procedure. Comparing each rank against its own threshold and
    stopping there - which is what this used to do - can reject a hypothesis while leaving a
    strictly smaller p-value un-rejected.
    """
    n = p_values.size
    reject = np.zeros(n, dtype=bool)
    if n == 0:
        return reject
    order = np.argsort(p_values)
    ranked = p_values[order]
    passing = np.flatnonzero(ranked <= (np.arange(1, n + 1) / n) * alpha)
    if passing.size:
        reject[order[: passing[-1] + 1]] = True
    return reject


def run_all_hypothesis_tests() -> pd.DataFrame:
    print("[REPORT] Running paired hypothesis tests H1-H30...")

    rows: List[Dict[str, Any]] = []
    for h in HYPOTHESES:
        result = _evaluate(h)
        if result is None:
            rows.append({
                "hypothesis_id": h.hid, "description": h.description,
                "test_name": "Not tested (input missing or empty)",
                "test_stat": np.nan, "p_value": np.nan, "wilcoxon_p_value": np.nan,
                "effect_size_cohen_d": np.nan, "n_pairs": 0, "n_months": 0,
                "mean_expiry": np.nan, "mean_control": np.nan,
                "stated_direction": h.direction, "direction_consistent": False,
                "note": f"{h.source}:{h.column}",
            })
        else:
            rows.append(result)

    summary = pd.DataFrame(rows)

    # Multiplicity correction over the hypotheses actually tested. Counting untested ones in
    # the denominator would make the correction depend on how much data happened to be
    # present, which is not a property of the hypotheses.
    tested = summary["p_value"].notna().to_numpy()
    n_tested = int(tested.sum())
    summary["n_tested"] = n_tested
    summary["alpha_bonferroni"] = ALPHA / n_tested if n_tested else np.nan
    summary["significant_bonferroni"] = tested & (
        summary["p_value"].to_numpy() < (ALPHA / n_tested if n_tested else np.inf))

    summary["significant_fdr"] = False
    if n_tested:
        summary.loc[tested, "significant_fdr"] = _benjamini_hochberg(
            summary.loc[tested, "p_value"].to_numpy(), ALPHA)

    # Rejection is not support. The test is two-sided, so a small p-value says the quantity
    # moved between expiry and control sessions - not that it moved the way the hypothesis
    # claimed. A directional hypothesis whose effect points the other way has been refuted,
    # and reporting it among the confirmations would invert its meaning.
    summary["supported"] = summary.significant_fdr & summary.direction_consistent.astype(bool)
    summary["contradicted"] = summary.significant_fdr & ~summary.direction_consistent.astype(bool)

    out_csv = Path(RESULTS_DIR) / "hypothesis_testing_summary.csv"
    summary.to_csv(out_csv, index=False)
    print(f"[DONE] {n_tested} of {len(summary)} hypotheses tested; "
          f"{int(summary.significant_fdr.sum())} differ at FDR {ALPHA} "
          f"({int(summary.supported.sum())} in the stated direction, "
          f"{int(summary.contradicted.sum())} against it). Saved to {out_csv}")
    return summary


if __name__ == "__main__":
    run_all_hypothesis_tests()
