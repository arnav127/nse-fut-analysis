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
HYPOTHESES: List[Hypothesis] = [
    H("H1",  "Basis volatility higher on expiry", "a2_basis_divergence.csv", "basis_std_dev", "mean"),
    H("H2",  "Basis divergence worse for illiquid stocks", "a2_basis_divergence.csv", "basis_range", "mean"),
    H("H3",  "Proprietary desk volume share higher on expiry", "a3_participant_profile.csv", "volume", "sum"),
    # "Shift" names no direction, so this one is genuinely two-sided.
    H("H4",  "Custodian trade counts shift on expiry", "a3_participant_profile.csv", "trades", "sum", "two"),
    H("H5",  "Algo volume share higher on expiry", "a4_algo_segmentation.csv", "total_volume", "sum"),
    H("H6",  "Algo order IOC rate higher on expiry", "a4_algo_segmentation.csv", "ioc_rate", "mean"),
    H("H7",  "Cancel-to-entry ratio spikes on expiry", "a5_cancellation_patterns.csv", "cancel_to_entry_ratio", "mean"),
    H("H8",  "Cancellations concentrated in prop/algo flow", "a5_cancellation_patterns.csv", "cancellations", "sum"),
    H("H9",  "Iceberg order ratio higher on expiry", "a6_iceberg_detection.csv", "iceberg_ratio", "mean"),
    H("H10", "Aggressive order ratio higher on expiry", "a7_ioc_aggressiveness.csv", "aggressive_ratio", "mean"),
    # H11 is about the *final* five minutes, so it is measured on the late sub-window only.
    # Averaging every minute from the window's open tests H10 again under another name.
    H("H11", "Aggressiveness accelerates in the final 5 minutes", "a7_ioc_aggressiveness.csv", "ioc_ratio", "mean",
      "+", ("sub_window", "Late")),
    H("H12", "Bid-ask spread widens on expiry", "b1_spread_dynamics.csv", "mean_spread_bps", "mean"),
    H("H13", "Spread widening worse for illiquid stocks", "b1_spread_dynamics.csv", "max_spread_bps", "mean"),
    # Erosion means less depth, so the stated direction is negative.
    H("H14", "Order book depth erosion on expiry", "b2_depth_erosion.csv", "avg_bid_depth", "mean", "-"),
    H("H15", "Depth erosion is asymmetric", "b2_depth_erosion.csv", "abs_imbalance", "mean"),
    H("H16", "Order flow imbalance higher on expiry", "b3_order_flow_imbalance.csv", "cash_ofi", "mean"),
    H("H17", "Price impact higher on expiry", "b4_price_impact.csv", "median_price_impact_bps", "mean"),
    H("H18", "Book pressure persistence higher on expiry", "b5_book_asymmetry.csv", "book_pressure_persistence", "mean"),
    H("H19", "Book pressure magnitude higher on expiry", "b5_book_asymmetry.csv", "mean_log_pressure", "mean"),
    H("H20", "VWAP drift direction matches roll pressure", "c3_directional_validation.csv", "match_vwap", "mean"),
    H("H21", "VWAP drift magnitude tracks roll intensity", "c3_directional_validation.csv", "roll_intensity", "mean"),
    H("H22", "Book asymmetry aligns with roll direction", "c3_directional_validation.csv", "match_book", "mean"),
    H("H23", "Basis mispricing larger on high roll intensity", "c2_cost_of_carry.csv", "mispricing_bps", "mean"),
    H("H24", "Settlement realised variance rate higher on expiry", "a8_volatility_regime.csv", "rv_ratio", "mean"),
    H("H25", "Trade concentration (HHI) higher on expiry", "a9_trade_clustering.csv", "hhi_concentration", "mean"),
    H("H26", "Futures returns Granger-cause cash returns on expiry", "a10_lead_lag.csv", "granger_f_stat", "mean"),
    H("H27", "Amihud illiquidity uplift higher on expiry", "a11_amihud_illiquidity.csv", "amihud_uplift", "mean"),
    H("H28", "Phantom order rate (<1s) higher on expiry", "a12_order_lifespan.csv", "phantom_order_rate", "mean"),
    H("H29", "Settlement volume Gini higher on expiry", "b6_volume_profile.csv", "volume_gini", "mean"),
    # "Differs" names no direction.
    H("H30", "Post-shock recovery time differs on expiry", "b7_market_resilience.csv", "mean_recovery_time_sec",
      "mean", "two"),
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
