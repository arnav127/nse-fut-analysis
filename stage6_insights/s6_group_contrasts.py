"""Two contrasts that turn "different on expiry" into something worth reporting.

Every paired test in the study answers the same question: is this quantity different on an
expiry Thursday from the matched control session? A rejection there is consistent with the
settlement mechanism and equally consistent with everything else that happens on the last
Thursday of a month - index rebalancing, month-end flows, option expiry on the index. The
matched design controls for the month; it does not control for the day.

Two differences-in-differences do control for it.

**Placebo.** Securities with no expiring derivative face no settlement incentive at all.
Taking the expiry-minus-control difference for each security and then comparing the
derivative groups against the placebo group asks whether the effect is about settlement or
about the calendar. If the placebo securities move the same way, the finding is a Thursday
effect and should be reported as one.

**Liquidity.** If the window is being influenced, the constraint is what it costs, and that
cost is far lower where the book is thin. Comparing the expiry-minus-control difference in
the illiquid group against the liquid group asks whether the effect is larger where acting
on the incentive is cheaper - which is a prediction the settlement story makes and the
alternatives mostly do not.

Both are computed on per-security paired differences, so each security contributes one
number to each side and the two-sample test is over securities rather than over
security-months. That costs power and is the honest unit: the twelve months of one security
are not twelve independent observations of that security's response.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scipy import stats  # noqa: E402

from config.settings import EXPIRY_CONTROL_PAIRS, RESULTS_DIR  # noqa: E402
from config.universe import group_of  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Contrasts", "stage6_insights.log")

# (results file, column, label) for the measures the contrasts are run on. Deliberately
# short: these are the headline quantities, and running the contrast over every column in
# every file would bury them under a hundred comparisons nobody specified in advance.
MEASURES: List[Tuple[str, str, str]] = [
    ("b1_spread_dynamics.csv", "mean_spread_bps", "Quoted spread (bps)"),
    ("b2_depth_erosion.csv", "avg_bid_depth", "Visible bid depth"),
    ("s1_settlement_price.csv", "abs_drift_bps", "|Settlement VWAP - open mid| (bps)"),
    ("s1_settlement_price.csv", "abs_reversal_bps", "|Settlement VWAP - close| (bps)"),
    ("s1_settlement_price.csv", "terminal_gap_bps", "|Final minute - window VWAP| (bps)"),
    ("s1_settlement_price.csv", "vwap_tracking_share", "Volume at the running VWAP"),
    ("s2_pressure_or_activity.csv", "variance_ratio", "Variance ratio (60s/1s)"),
    ("s2_pressure_or_activity.csv", "flow_autocorr", "Signed flow persistence"),
    ("s2_pressure_or_activity.csv", "permanent_share", "Permanent share of impact"),
    ("s3_hidden_liquidity.csv", "concealed_depth_share", "Concealed share of resting size"),
    ("s3_hidden_liquidity.csv", "concealed_size_multiple", "Concealed parent size multiple"),
    ("s3_hidden_liquidity.csv", "replenishment_rate", "Replenishments per 1000 matched"),
    ("s4_marking_cost.csv", "move_bps_0p1", "Price move per 0.1 cr swept (bps)"),
    ("a12_order_lifespan.csv", "phantom_order_rate", "Orders cancelled within one second"),
    ("a5_cancellation_patterns.csv", "cancel_to_entry_ratio", "Cancellations per entry"),
]


def _paired_differences(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Mean expiry-minus-control difference for each security, over the matched months."""
    if frame.empty or column not in frame.columns:
        return pd.DataFrame()
    needed = {"symbol", "trade_date", column}
    if not needed <= set(frame.columns):
        return pd.DataFrame()

    work = frame[["symbol", "trade_date", column]].copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan).dropna()
    if work.empty:
        return pd.DataFrame()
    work["session"] = pd.to_datetime(work.trade_date, errors="coerce").dt.strftime("%d%m%Y")
    # One value per security-session before pairing: several results files carry finer
    # breakdowns, and pairing without reducing them forms a cross product.
    work = work.groupby(["symbol", "session"], as_index=False)[column].mean()
    lookup = {(row.symbol, row.session): getattr(row, column) for row in work.itertuples()}

    records = []
    for symbol in work.symbol.unique():
        diffs = [lookup[(symbol, e)] - lookup[(symbol, c)]
                 for e, c in EXPIRY_CONTROL_PAIRS
                 if (symbol, e) in lookup and (symbol, c) in lookup]
        if not diffs:
            continue
        records.append({
            "symbol": symbol,
            "security_group": group_of(symbol),
            "mean_difference": float(np.mean(diffs)),
            "months": len(diffs),
        })
    return pd.DataFrame(records)


def _contrast(differences: pd.DataFrame, treated: List[str], reference: List[str]) -> Dict:
    """Two-sample comparison of per-security differences between two sets of groups."""
    a = differences[differences.security_group.isin(treated)].mean_difference.to_numpy()
    b = differences[differences.security_group.isin(reference)].mean_difference.to_numpy()
    if a.size < 3 or b.size < 3:
        return {}
    # Welch, not Student: the groups differ in liquidity by construction and therefore in
    # the variance of almost every quantity measured here, which is exactly the case the
    # equal-variance assumption gets wrong.
    t_stat, p_value = stats.ttest_ind(a, b, equal_var=False)
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    return {
        "treated_n": int(a.size),
        "reference_n": int(b.size),
        "treated_mean": float(a.mean()),
        "reference_mean": float(b.mean()),
        "difference_in_differences": float(a.mean() - b.mean()),
        "t_stat": float(t_stat),
        "p_value": float(p_value),
        "cohen_d": float((a.mean() - b.mean()) / pooled) if pooled > 0 else np.nan,
    }


def run_s6_group_contrasts() -> pd.DataFrame:
    out_csv = Path(RESULTS_DIR) / "s6_group_contrasts.csv"
    detail_csv = Path(RESULTS_DIR) / "s6_paired_differences.csv"
    logger.info("[S6] placebo and liquidity contrasts")

    rows = []
    detail_frames = []
    for file_name, column, label in MEASURES:
        path = Path(RESULTS_DIR) / file_name
        if not path.exists():
            logger.info(f"[S6] {file_name} absent; {label} skipped")
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue

        differences = _paired_differences(frame, column)
        if differences.empty:
            continue
        differences["measure"] = label
        detail_frames.append(differences)

        groups = set(differences.security_group)
        for name, treated, reference in (
            ("settlement vs calendar", ["liquid", "illiquid"], ["placebo"]),
            ("illiquid vs liquid", ["illiquid"], ["liquid"]),
        ):
            if not (set(treated) & groups) or not (set(reference) & groups):
                continue
            result = _contrast(differences, treated, reference)
            if not result:
                continue
            rows.append({"measure": label, "source": f"{file_name}:{column}",
                         "contrast": name, **result})

    summary = pd.DataFrame(rows)
    summary.to_csv(out_csv, index=False)
    if detail_frames:
        pd.concat(detail_frames, ignore_index=True).to_csv(detail_csv, index=False)

    if summary.empty:
        logger.warning("[S6] no contrasts could be computed")
    else:
        placebo = summary[summary.contrast == "settlement vs calendar"]
        if placebo.empty:
            logger.warning("[S6] no placebo group in the universe; the settlement-versus-"
                           "calendar contrast could not be run, and every expiry result "
                           "remains open to a calendar explanation")
        logger.info(f"[S6] {len(summary)} contrasts -> {out_csv}")
    return summary


if __name__ == "__main__":
    frame = run_s6_group_contrasts()
    if not frame.empty:
        pd.set_option("display.width", 200)
        print(frame[["measure", "contrast", "treated_mean", "reference_mean",
                     "difference_in_differences", "p_value"]].to_string(index=False))
