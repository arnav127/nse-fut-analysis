"""Orchestrator for Stage 5 CLOB-based analysis modules (B1-B7)."""

from stage5_clob_analysis.b1_spread_dynamics import run_b1_spread_dynamics
from stage5_clob_analysis.b2_depth_erosion import run_b2_depth_erosion
from stage5_clob_analysis.b3_order_flow_imbalance import run_b3_order_flow_imbalance
from stage5_clob_analysis.b4_price_impact import run_b4_price_impact
from stage5_clob_analysis.b5_book_asymmetry import run_b5_book_asymmetry
from stage5_clob_analysis.b6_volume_profile import run_b6_volume_profile
from stage5_clob_analysis.b7_market_resilience import run_b7_market_resilience


def run_clob_analysis() -> None:
    print("\n=== STAGE 5: CLOB-BASED ANALYSIS (B1-B7 via DUCKDB) ===")
    run_b1_spread_dynamics()
    run_b2_depth_erosion()
    run_b3_order_flow_imbalance()
    run_b4_price_impact()
    run_b5_book_asymmetry()
    run_b6_volume_profile()
    run_b7_market_resilience()
    print("\n[COMPLETE] Stage 5 CLOB analysis finished.")


if __name__ == "__main__":
    run_clob_analysis()
