"""Orchestrator for Stage 5 CLOB-based analysis modules (B1-B7)."""

import time

from stage5_clob_analysis.b1_spread_dynamics import run_b1_spread_dynamics
from stage5_clob_analysis.b2_depth_erosion import run_b2_depth_erosion
from stage5_clob_analysis.b3_order_flow_imbalance import run_b3_order_flow_imbalance
from stage5_clob_analysis.b4_price_impact import run_b4_price_impact
from stage5_clob_analysis.b5_book_asymmetry import run_b5_book_asymmetry
from stage5_clob_analysis.b6_volume_profile import run_b6_volume_profile
from stage5_clob_analysis.b7_market_resilience import run_b7_market_resilience


def run_clob_analysis() -> None:
    print("\n=== STAGE 5: CLOB-BASED ANALYSIS (B1-B7 via DUCKDB) ===")
    t_start = time.time()

    modules = [
        ("B1: Spread Dynamics", run_b1_spread_dynamics),
        ("B2: Depth Erosion", run_b2_depth_erosion),
        ("B3: Order Flow Imbalance", run_b3_order_flow_imbalance),
        ("B4: Price Impact", run_b4_price_impact),
        ("B5: Book Asymmetry", run_b5_book_asymmetry),
        ("B6: Volume Profile", run_b6_volume_profile),
        ("B7: Market Resilience", run_b7_market_resilience),
    ]

    for name, func in modules:
        t0 = time.time()
        func()
        print(f"[TIMING] Module {name} finished in {time.time() - t0:.2f}s")

    print(f"\n[COMPLETE] Stage 5 CLOB analysis finished in {time.time() - t_start:.2f}s")


if __name__ == "__main__":
    run_clob_analysis()
