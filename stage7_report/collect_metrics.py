"""Compute every quantity the manuscript states, and record it.

This is the only place the paper's numbers come from. The manuscript cites macros; the
macros are built from `data/results/metrics.json`; this module is what fills that file. A
number that is not recorded here cannot appear in the paper, which is the property that
makes the document re-derivable rather than merely plausible.

Three groups.

*Sample scale* - how much data the study is built on. Read from the stage-1 manifests
nsetick writes beside each session's partitions, so the counts are what the parser actually
emitted rather than what the configuration asked for.

*Stylised facts* - the descriptive quantities the results section leads with: spreads,
depth, iceberg usage, participant composition, hidden size. Aggregated from the stage-3 and
stage-5 outputs.

*Test results* - one macro per hypothesis for the statistic, p-value and effect size, so the
prose can name any of them without a literal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    ALL_TARGET_DATES,
    CLOB_DEPTH_LEVELS,
    CLOB_REPORTED_LEVELS,
    CLOB_SNAPSHOT_INTERVAL_SECONDS,
    CONTROL_DAYS_DDMMYYYY,
    EXPIRY_THURSDAYS_DDMMYYYY,
    ILLIQUID_SYMBOLS,
    LIQUID_SYMBOLS,
    PARSED_DATA_DIR,
    RESULTS_DIR,
    SETTLEMENT_WINDOW_END,
    SETTLEMENT_WINDOW_START,
    TARGET_SYMBOLS,
)
from utils.logger import setup_logger  # noqa: E402
from utils.paths import clob_dir, parsed_dir  # noqa: E402
from utils.provenance import Run  # noqa: E402

logger = setup_logger("Metrics", "stage7_report.log")


def _csv(name: str) -> pd.DataFrame:
    path = Path(RESULTS_DIR) / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _mean_by_expiry(df: pd.DataFrame, column: str) -> tuple[Optional[float], Optional[float]]:
    """Mean of `column` on expiry sessions and on control sessions."""
    if df.empty or column not in df.columns or "is_expiry" not in df.columns:
        return None, None
    values = pd.to_numeric(df[column], errors="coerce")
    flag = df["is_expiry"].astype(bool)
    frame = pd.DataFrame({"v": values, "e": flag}).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return None, None
    expiry = frame.loc[frame.e, "v"]
    control = frame.loc[~frame.e, "v"]
    return (float(expiry.mean()) if len(expiry) else None,
            float(control.mean()) if len(control) else None)


def _record_pair(run: Run, stem: str, df: pd.DataFrame, column: str, unit: str, note: str) -> None:
    """Record the expiry mean, the control mean and the difference for one quantity."""
    expiry, control = _mean_by_expiry(df, column)
    run.record(f"{stem}_expiry", expiry, unit, note)
    run.record(f"{stem}_control", control, unit, note)
    if expiry is not None and control is not None:
        run.record(f"{stem}_diff", expiry - control, unit, f"{note} (expiry minus control)")
        if control:
            run.record(f"{stem}_pct_change", (expiry - control) / abs(control) * 100.0,
                       "per cent", f"{note} (expiry relative to control)")


def _design(run: Run) -> None:
    """The study design: what was specified, independent of what the data turned out to be."""
    run.record("design.sessions", len(ALL_TARGET_DATES), "sessions",
               "expiry Thursdays plus matched control sessions")
    run.record("design.expiry_sessions", len(EXPIRY_THURSDAYS_DDMMYYYY), "sessions", "")
    run.record("design.control_sessions", len(CONTROL_DAYS_DDMMYYYY), "sessions", "")
    run.record("design.symbols", len(TARGET_SYMBOLS), "securities", "study universe")
    run.record("design.liquid_symbols", len(LIQUID_SYMBOLS), "securities", "")
    run.record("design.illiquid_symbols", len(ILLIQUID_SYMBOLS), "securities", "")
    run.record("design.window_start", SETTLEMENT_WINDOW_START, "IST", "settlement window open")
    run.record("design.window_end", SETTLEMENT_WINDOW_END, "IST", "settlement window close")
    run.record("design.window_minutes", 30, "minutes", "settlement window length")
    run.record("design.book_levels", CLOB_DEPTH_LEVELS, "levels", "book depth reconstructed")
    run.record("design.reported_levels", CLOB_REPORTED_LEVELS, "levels",
               "levels carried into the snapshot table")
    # Recorded as an integer when it is whole, so the prose reads "every one second" rather
    # than "every 1.00 second".
    interval = CLOB_SNAPSHOT_INTERVAL_SECONDS
    run.record("design.snapshot_interval",
               int(interval) if float(interval).is_integer() else interval,
               "seconds", "book snapshot cadence")
    run.record("design.liquid_list", ", ".join(LIQUID_SYMBOLS), "", "")
    run.record("design.illiquid_list", ", ".join(ILLIQUID_SYMBOLS), "", "")


def _sample(run: Run) -> None:
    """Sample scale, from the manifests nsetick writes alongside each session's output.

    Counting from the manifests rather than from the configuration is the point: it reports
    what was parsed. A session whose raw file is missing contributes nothing and the totals
    say so, instead of the paper claiming twenty-four sessions it never read.
    """
    totals = {"orders_read": 0, "orders_kept": 0, "trades_read": 0, "trades_kept": 0}
    sessions_parsed = []

    for session in ALL_TARGET_DATES:
        present = False
        for category, prefix in (("cash_orders", "orders"), ("cash_trades", "trades")):
            directory = parsed_dir(category, session)
            for manifest in directory.glob("_manifest*.json"):
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                totals[f"{prefix}_read"] += int(payload.get("rows_read", 0))
                totals[f"{prefix}_kept"] += int(payload.get("rows_emitted", 0))
                present = True
        if present:
            sessions_parsed.append(session)

    run.record("sample.sessions_parsed", len(sessions_parsed), "sessions",
               "sessions with stage-1 output present")
    run.record("sample.expiry_parsed",
               sum(1 for s in sessions_parsed if s in EXPIRY_THURSDAYS_DDMMYYYY),
               "sessions", "")
    run.record("sample.order_events_read", totals["orders_read"], "records",
               "order records decoded from the raw feed, all symbols")
    run.record("sample.order_events", totals["orders_kept"], "records",
               "order records retained for the study universe")
    run.record("sample.order_events_millions", totals["orders_kept"] / 1e6, "millions", "")
    run.record("sample.trades_read", totals["trades_read"], "records",
               "trade records decoded from the raw feed, all symbols")
    run.record("sample.trades", totals["trades_kept"], "records",
               "trade records retained for the study universe")
    run.record("sample.trades_millions", totals["trades_kept"] / 1e6, "millions", "")
    if totals["orders_read"]:
        run.record("sample.universe_share_pct",
                   totals["orders_kept"] / totals["orders_read"] * 100.0, "per cent",
                   "share of all EQ order records belonging to the study universe")

    snapshots = 0
    symbols = set()
    for session in ALL_TARGET_DATES:
        for part in clob_dir(session).glob("sym=*"):
            symbols.add(part.name.split("=", 1)[1])
    snapshot_files = [p for s in ALL_TARGET_DATES for p in clob_dir(s).glob("sym=*/*.parquet")]
    if snapshot_files:
        import duckdb
        pattern = (Path(PARSED_DATA_DIR).parent / "clob_snapshots" / "date=*" / "sym=*" / "*.parquet").as_posix()
        with duckdb.connect() as conn:
            snapshots = int(conn.execute(
                f"SELECT count(*) FROM read_parquet('{pattern}')").fetchone()[0])
    run.record("sample.snapshots", snapshots, "snapshots",
               "one-second book snapshots inside the settlement window")
    run.record("sample.snapshots_thousands", snapshots / 1e3, "thousands", "")
    run.record("sample.snapshot_symbols", len(symbols), "securities",
               "securities with reconstructed books")


def _stylised(run: Run) -> None:
    """The descriptive quantities the results section leads with."""
    spread = _csv("b1_spread_dynamics.csv")
    _record_pair(run, "spread.mean_bps", spread, "mean_spread_bps", "basis points",
                 "time-weighted mean quoted spread over the settlement window")
    _record_pair(run, "spread.max_bps", spread, "max_spread_bps", "basis points",
                 "widest one-second spread in the window")
    _record_pair(run, "spread.open_bps", spread, "spread_at_1500", "basis points", "spread at 15:00")
    _record_pair(run, "spread.close_bps", spread, "spread_at_1530", "basis points", "spread at 15:30")
    if not spread.empty and "liquidity_group" in spread.columns:
        for group in ("Liquid", "Illiquid"):
            subset = spread[spread.liquidity_group == group]
            _record_pair(run, f"spread.{group.lower()}_bps", subset, "mean_spread_bps",
                         "basis points", f"mean spread, {group.lower()} group")

    depth = _csv("b2_depth_erosion.csv")
    _record_pair(run, "depth.bid", depth, "avg_bid_depth", "shares",
                 "mean visible bid depth over the reported levels")
    _record_pair(run, "depth.ask", depth, "avg_ask_depth", "shares", "mean visible ask depth")
    _record_pair(run, "depth.imbalance", depth, "avg_book_imbalance", "ratio",
                 "mean signed book imbalance")
    _record_pair(run, "depth.abs_imbalance", depth, "abs_imbalance", "ratio",
                 "mean absolute book imbalance")

    iceberg = _csv("a6_iceberg_detection.csv")
    _record_pair(run, "ice.ratio", iceberg, "iceberg_ratio", "fraction",
                 "share of entered orders carrying a disclosed quantity below their total")
    _record_pair(run, "ice.hidden_share", iceberg, "hidden_volume_ratio", "fraction",
                 "share of entered volume held back from display")
    if not iceberg.empty and "participant_type" in iceberg.columns:
        for participant in ("Custodian", "Proprietary", "NCNP"):
            subset = iceberg[iceberg.participant_type == participant]
            _record_pair(run, f"ice.{participant.lower()}_ratio", subset, "iceberg_ratio",
                         "fraction", f"iceberg usage, {participant}")

    cancels = _csv("a5_cancellation_patterns.csv")
    _record_pair(run, "cancel.ratio", cancels, "cancel_to_entry_ratio", "ratio",
                 "cancellations per entry inside the window")

    aggression = _csv("a7_ioc_aggressiveness.csv")
    _record_pair(run, "ioc.ratio", aggression, "ioc_ratio", "fraction",
                 "immediate-or-cancel share of entered orders")
    _record_pair(run, "ioc.aggressive_ratio", aggression, "aggressive_ratio", "fraction",
                 "immediate-or-cancel plus market share of entered orders")
    if not aggression.empty and "sub_window" in aggression.columns:
        late = aggression[aggression.sub_window == "Late"]
        early = aggression[aggression.sub_window == "Early"]
        _record_pair(run, "ioc.late_ratio", late, "ioc_ratio", "fraction",
                     "immediate-or-cancel share, final five minutes")
        _record_pair(run, "ioc.early_ratio", early, "ioc_ratio", "fraction",
                     "immediate-or-cancel share, 15:00 to 15:25")

    impact = _csv("b4_price_impact.csv")
    _record_pair(run, "impact.median_bps", impact, "median_price_impact_bps", "basis points",
                 "median absolute trade-to-trade price change")
    _record_pair(run, "impact.kyle_lambda", impact, "kyle_lambda", "rupees per share",
                 "minute price change regressed on tick-rule signed volume")
    _record_pair(run, "impact.kyle_r2", impact, "kyle_r2", "fraction",
                 "coefficient of determination of that regression")

    lifespan = _csv("a12_order_lifespan.csv")
    _record_pair(run, "life.median_sec", lifespan, "median_lifespan_sec", "seconds",
                 "median time from entry to cancellation")
    _record_pair(run, "life.phantom_rate", lifespan, "phantom_order_rate", "fraction",
                 "share of cancelled orders resting under one second")

    volatility = _csv("a8_volatility_regime.csv")
    _record_pair(run, "vol.rv_ratio", volatility, "rv_ratio", "ratio",
                 "settlement realised variance per minute over the rest of the session")

    amihud = _csv("a11_amihud_illiquidity.csv")
    _record_pair(run, "illiq.uplift", amihud, "amihud_uplift", "fraction",
                 "settlement Amihud illiquidity relative to the rest of the session")

    clustering = _csv("a9_trade_clustering.csv")
    _record_pair(run, "cluster.hhi", clustering, "hhi_concentration", "index",
                 "Herfindahl index of traded volume across the window's minutes")

    profile = _csv("b6_volume_profile.csv")
    _record_pair(run, "profile.gini", profile, "volume_gini", "index",
                 "Gini coefficient of traded volume across the window's minutes")
    _record_pair(run, "profile.final_min_share", profile, "final_min_share", "fraction",
                 "share of settlement volume traded in the final minute")
    _record_pair(run, "profile.last_five_share", profile, "last_five_min_share", "fraction",
                 "share of settlement volume traded in the final five minutes")

    resilience = _csv("b7_market_resilience.csv")
    _record_pair(run, "resil.shocks", resilience, "n_shocks", "episodes",
                 "spread widenings beyond twice the session median")
    _record_pair(run, "resil.recovery_sec", resilience, "median_recovery_time_sec", "seconds",
                 "median time for a widened spread to return inside 1.5 times the median")

    asymmetry = _csv("b5_book_asymmetry.csv")
    _record_pair(run, "press.persistence", asymmetry, "book_pressure_persistence", "fraction",
                 "share of snapshots whose imbalance matches the session's mean direction")

    flow = _csv("b3_order_flow_imbalance.csv")
    _record_pair(run, "flow.ofi", flow, "cash_ofi", "ratio",
                 "net submitted volume as a share of total submitted volume")

    participants = _csv("a3_participant_profile.csv")
    if not participants.empty and {"participant_type", "volume"} <= set(participants.columns):
        window = participants[participants.is_settlement_window.astype(bool)] \
            if "is_settlement_window" in participants.columns else participants
        total = window.volume.sum()
        if total:
            for participant in ("Custodian", "Proprietary", "NCNP"):
                share = window.loc[window.participant_type == participant, "volume"].sum() / total * 100.0
                run.record(f"part.{participant.lower()}_share_pct", float(share), "per cent",
                           f"{participant} share of settlement-window traded volume, both sides")


def _tests(run: Run) -> None:
    """One set of macros per hypothesis, so the prose can name any of them."""
    summary = _csv("hypothesis_testing_summary.csv")
    if summary.empty:
        return

    tested = summary[summary.p_value.notna()] if "p_value" in summary else summary.iloc[0:0]
    run.record("test.specified", len(summary), "hypotheses", "hypotheses in the design")
    run.record("test.evaluated", len(tested), "hypotheses",
               "hypotheses whose inputs were present")
    run.record("test.alpha", 0.05, "", "nominal significance level")
    rejected = (summary[summary.significant_fdr.astype(bool)]
                if "significant_fdr" in summary else summary.iloc[0:0])
    run.record("test.rejected_fdr", len(rejected), "hypotheses",
               "rejected under Benjamini-Hochberg control of the false discovery rate")
    run.record("test.rejected_ids", ", ".join(rejected.hypothesis_id.astype(str)) or "none",
               "", "")
    run.record("test.rejected_bonferroni",
               int(summary.significant_bonferroni.astype(bool).sum())
               if "significant_bonferroni" in summary else 0, "hypotheses", "")
    # Recorded unconditionally, zero included. A quantity that appears only when some
    # tests ran leaves the manuscript citing a macro that does not exist on a partial run,
    # which is a build failure rather than a sentence reading "0".
    run.record("test.pairs_total", int(tested.n_pairs.sum()) if len(tested) else 0, "pairs",
               "matched security-session pairs across all evaluated hypotheses")
    run.record("test.pairs_median", float(tested.n_pairs.median()) if len(tested) else 0.0,
               "pairs", "median pairs behind a test")
    run.record("test.months_median", float(tested.n_months.median()) if len(tested) else 0.0,
               "months", "median expiry-control months behind a test")
    untested = summary[summary.p_value.isna()] if "p_value" in summary else summary
    run.record("test.untested_ids", ", ".join(untested.hypothesis_id.astype(str)) or "none", "", "")

    for row in summary.itertuples(index=False):
        stem = f"h.{str(row.hypothesis_id).lower()}"
        run.record(f"{stem}.desc", str(row.description), "", "")
        for field, unit in (("test_stat", ""), ("p_value", ""), ("wilcoxon_p_value", ""),
                            ("effect_size_cohen_d", ""), ("n_pairs", "pairs"),
                            ("mean_expiry", ""), ("mean_control", "")):
            value = getattr(row, field, None)
            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                run.record(f"{stem}.{field}", float(value) if field != "n_pairs" else int(value),
                           unit, str(row.description))
        if hasattr(row, "significant_fdr"):
            run.record(f"{stem}.significant", "yes" if bool(row.significant_fdr) else "no", "", "")


def collect_all() -> None:
    logger.info("[METRICS] recording the quantities the manuscript cites")
    with Run("stage7.collect_metrics") as run:
        _design(run)
        _sample(run)
        _stylised(run)
        _tests(run)
    from utils.provenance import load_metrics
    logger.info(f"[METRICS] {len(load_metrics())} quantities recorded")


if __name__ == "__main__":
    collect_all()
