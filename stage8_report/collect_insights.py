"""Record the quantities the settlement-window sections of the report cite.

Separate from `collect_metrics` because these come from stage 6 rather than from stages 3 and
5, and because keeping them apart makes it obvious which numbers depend on the new analysis
and which on the original measures.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402
from config.settings import CONTROL_DAYS_DDMMYYYY  # noqa: E402
from config.universe import (  # noqa: E402
    GROUP_SIZE,
    GROUPS,
    MAX_RANK_SPAN,
    META,
    MIN_TRADES_PER_SESSION,
    is_derived_universe,
)
from stage6_insights.s2_pressure_or_activity import VR_HORIZON_SECONDS  # noqa: E402
from stage6_insights.s4_marking_cost import PROBE_NOTIONAL_CR  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.provenance import Run  # noqa: E402

logger = setup_logger("Insights", "stage8_report.log")


def _csv(name: str) -> pd.DataFrame:
    path = Path(RESULTS_DIR) / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _split(frame: pd.DataFrame, column: str) -> tuple:
    if frame.empty or column not in frame.columns or "is_expiry" not in frame.columns:
        return None, None
    values = pd.to_numeric(frame[column], errors="coerce")
    flag = frame.is_expiry.astype(bool)
    clean = pd.DataFrame({"v": values, "e": flag}).replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None, None
    expiry, control = clean.loc[clean.e, "v"], clean.loc[~clean.e, "v"]
    return (float(expiry.mean()) if len(expiry) else None,
            float(control.mean()) if len(control) else None)


def _pair(run: Run, stem: str, frame: pd.DataFrame, column: str, unit: str, note: str) -> None:
    expiry, control = _split(frame, column)
    run.record(f"{stem}_expiry", expiry, unit, note)
    run.record(f"{stem}_control", control, unit, note)
    if expiry is not None and control is not None:
        run.record(f"{stem}_diff", expiry - control, unit, f"{note} (expiry minus control)")


def _placebo_note(contrasts: pd.DataFrame) -> str:
    """One sentence on what the placebo comparison did or did not establish."""
    if contrasts.empty:
        return ("The contrasts could not be computed: the inputs they draw on were not "
                "produced by this run.")
    placebo = contrasts[contrasts.contrast == "settlement vs calendar"]
    if placebo.empty:
        return ("No placebo securities are in the universe for this run, so the comparison "
                "that would separate a settlement effect from a last-Thursday-of-the-month "
                "effect could not be made. Every expiry result above therefore remains open "
                "to a calendar explanation, and should be read with that in mind. Running "
                "the universe builder with a derivatives-eligibility list populates the "
                "group and closes this gap.")
    significant = placebo[placebo.p_value < 0.05]
    if significant.empty:
        return (f"Across {len(placebo)} measures, none of the expiry-day differences is "
                f"significantly larger in the derivatives groups than in the placebo group. "
                f"That is evidence against a settlement-specific explanation and for a "
                f"calendar one, and it is the more conservative reading of everything above.")
    names = ", ".join(significant.measure.astype(str))
    return (f"Of {len(placebo)} measures, {len(significant)} differ significantly between "
            f"the derivatives groups and the placebo group ({names}). For those the expiry "
            f"effect is specific to securities with an expiring contract rather than a "
            f"property of the calendar date.")


def collect_insight_metrics() -> None:
    logger.info("[INSIGHTS] recording settlement-window quantities")
    with Run("stage8.collect_insights") as run:
        run.record("probe.size_cr", PROBE_NOTIONAL_CR[0], "crore",
                   "notional swept through the displayed book")
        run.record("vr.horizon_seconds", VR_HORIZON_SECONDS, "seconds",
                   "long horizon of the variance ratio")
        run.record("universe.derived", "yes" if is_derived_universe() else "no", "",
                   "whether group membership was derived from the tape or taken from the "
                   "development list")
        for group in GROUPS.values():
            run.record(f"group.{group.key}_n", len(group.symbols), "securities", group.label)

        # The selection cascade, so the report can state how many securities each criterion
        # removed rather than only how many survived. A filter whose effect is not reported
        # is a researcher degree of freedom the reader cannot see.
        filters = META.get("filters") or {}
        run.record("select.traded", filters.get("symbols_traded"), "securities",
                   "securities that traded at all in the parsed sessions")
        run.record("select.complete", filters.get("after_present_in_all_sessions"), "securities",
                   "of those, present in every session")
        run.record("select.active", filters.get("after_activity_floor"), "securities",
                   "of those, above the activity floor")
        run.record("select.stable", filters.get("after_rank_stability"), "securities",
                   "of those, with a stable turnover rank across the year")
        # Criteria fall back to the configured values: they describe the procedure, which
        # is defined whether or not it has been run on this machine.
        run.record("select.min_trades",
                   filters.get("min_trades_per_session", MIN_TRADES_PER_SESSION), "trades",
                   "activity floor, median trades per control session")
        run.record("select.max_rank_span",
                   filters.get("max_rank_span", MAX_RANK_SPAN), "fraction",
                   "largest permitted interdecile span of a security's turnover rank")
        run.record("select.group_size", META.get("group_size", GROUP_SIZE),
                   "securities", "securities per group")
        run.record("select.control_sessions",
                   META.get("control_sessions", len(CONTROL_DAYS_DDMMYYYY)), "sessions",
                   "sessions used to rank securities; expiry sessions are excluded")
        run.record("select.fo_verified",
                   "yes" if META.get("fo_verified") else "no", "",
                   "whether derivatives eligibility was checked against a published list")
        overlap = META.get("placebo_adv_overlap") or {}
        for name, share in overlap.items():
            run.record(f"select.placebo_overlap_{name}", float(share), "fraction",
                       f"share of the {name} group inside the placebo group's turnover range")

        settlement = _csv("s1_settlement_price.csv")
        _pair(run, "abs.drift_bps", settlement, "abs_drift_bps", "basis points",
              "settlement VWAP against the mid at the window's open")
        _pair(run, "abs.reversal_bps", settlement, "abs_reversal_bps", "basis points",
              "settlement VWAP against the closing price")
        _pair(run, "terminal.gap_bps", settlement, "terminal_gap_bps", "basis points",
              "final minute's VWAP against the window's")
        _pair(run, "vwap.tracking_share", settlement, "vwap_tracking_share", "fraction",
              "volume transacted within a basis point of the running VWAP")
        _pair(run, "final.minute_share", settlement, "final_minute_volume_share", "fraction",
              "share of window volume traded in the final minute")

        pressure = _csv("s2_pressure_or_activity.csv")
        _pair(run, "variance.ratio", pressure, "variance_ratio", "ratio",
              "variance of a long-horizon mid return over the scaled one-second variance")
        _pair(run, "flow.persistence", pressure, "flow_autocorr", "correlation",
              "first-order autocorrelation of signed volume per second")
        _pair(run, "impact.permanent_share", pressure, "permanent_share", "ratio",
              "share of a flow-driven price move still present after a minute")
        _pair(run, "impact.short_bps", pressure, "impact_short_bps", "basis points",
              "mid move ten seconds after a second of substantial one-sided flow")

        hidden = _csv("s3_hidden_liquidity.csv")
        _pair(run, "concealed.depth_share", hidden, "concealed_depth_share", "fraction",
              "share of resting quantity that is not displayed")
        _pair(run, "concealed.size_multiple", hidden, "concealed_size_multiple", "ratio",
              "mean size of a concealing order over a plain one")
        _pair(run, "concealed.replenishment_rate", hidden, "replenishment_rate", "ratio",
              "replenishments per thousand shares matched")

        cost = _csv("s4_marking_cost.csv")
        tag = f"{PROBE_NOTIONAL_CR[0]:g}".replace(".", "p")
        _pair(run, "move.bps_small", cost, f"move_bps_{tag}", "basis points",
              f"price move from sweeping {PROBE_NOTIONAL_CR[0]} crore of displayed book")
        _pair(run, "book.visible_cr", cost, "visible_notional_cr", "crore",
              "displayed notional across the reported levels")
        if not cost.empty and "security_group" in cost.columns:
            for key in ("liquid", "illiquid", "placebo"):
                subset = cost[cost.security_group == key]
                if subset.empty:
                    continue
                value = pd.to_numeric(subset[f"move_bps_{tag}"], errors="coerce").median()
                run.record(f"move.bps_small_{key}", float(value) if pd.notna(value) else None,
                           "basis points", f"price move per probe, {key} group")

        contrasts = _csv("s6_group_contrasts.csv")
        run.record("contrast.count", len(contrasts), "contrasts", "")
        run.record("contrast.placebo_note", _placebo_note(contrasts), "",
                   "what the placebo comparison established on this run")

    from utils.provenance import load_metrics
    logger.info(f"[INSIGHTS] store now holds {len(load_metrics())} quantities")


if __name__ == "__main__":
    collect_insight_metrics()
