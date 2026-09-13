"""Stage 6 orchestrator.

Order matters here in a way it does not in the earlier analysis stages: S6 reads the outputs
of S1 through S4, so the contrasts run last. Everything before that is independent.
"""

from __future__ import annotations

import time

from stage6_insights.s1_settlement_price import run_s1_settlement_price
from stage6_insights.s2_pressure_or_activity import run_s2_pressure_or_activity
from stage6_insights.s3_hidden_liquidity import run_s3_hidden_liquidity
from stage6_insights.s4_marking_cost import run_s4_marking_cost
from stage6_insights.s5_window_profile import run_s5_window_profile
from stage6_insights.s6_group_contrasts import run_s6_group_contrasts
from utils.logger import setup_logger

logger = setup_logger("Stage6", "stage6_insights.log")

MODULES = [
    ("S1: settlement price and its benchmarks", run_s1_settlement_price),
    ("S2: pressure or activity", run_s2_pressure_or_activity),
    ("S3: concealed liquidity", run_s3_hidden_liquidity),
    ("S4: cost of moving the book", run_s4_marking_cost),
    ("S5: minute-by-minute window profile", run_s5_window_profile),
    ("S6: placebo and liquidity contrasts", run_s6_group_contrasts),
]


def run_insights() -> None:
    logger.info("=== STAGE 6: SETTLEMENT-WINDOW ANALYSIS ===")
    started = time.time()
    for name, function in MODULES:
        t0 = time.time()
        try:
            frame = function()
            rows = 0 if frame is None else len(frame)
            logger.info(f"[TIMING] {name}: {rows:,} rows in {time.time() - t0:.1f}s")
        except Exception as exc:
            logger.error(f"[FAILED] {name}: {exc}")
    logger.info(f"[COMPLETE] stage 6 finished in {time.time() - started:.1f}s")


if __name__ == "__main__":
    run_insights()
