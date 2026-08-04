"""Orchestrator for Stage 3 trade-level analysis modules (A1-A12)."""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage3_analysis.a10_lead_lag import run_a10_lead_lag
from stage3_analysis.a11_amihud_illiquidity import run_a11_amihud_illiquidity
from stage3_analysis.a12_order_lifespan import run_a12_order_lifespan
from stage3_analysis.a1_vwap_trajectory import run_a1_vwap_trajectory
from stage3_analysis.a2_basis_divergence import run_a2_basis_divergence
from stage3_analysis.a3_participant_profile import run_a3_participant_profile
from stage3_analysis.a4_algo_segmentation import run_a4_algo_segmentation
from stage3_analysis.a5_cancellation_patterns import run_a5_cancellation_patterns
from stage3_analysis.a6_iceberg_detection import run_a6_iceberg_detection
from stage3_analysis.a7_ioc_aggressiveness import run_a7_ioc_aggressiveness
from stage3_analysis.a8_volatility_regime import run_a8_volatility_regime
from stage3_analysis.a9_trade_clustering import run_a9_trade_clustering


def run_analysis() -> None:
    print("\n=== STAGE 3: TRADE-LEVEL ANALYSIS (A1-A12 via DUCKDB) ===")
    t_start = time.time()

    modules = [
        ("A1: VWAP Trajectory", run_a1_vwap_trajectory),
        ("A2: Basis Divergence", run_a2_basis_divergence),
        ("A3: Participant Profile", run_a3_participant_profile),
        ("A4: Algo Segmentation", run_a4_algo_segmentation),
        ("A5: Cancellation Patterns", run_a5_cancellation_patterns),
        ("A6: Iceberg Detection", run_a6_iceberg_detection),
        ("A7: IOC Aggressiveness", run_a7_ioc_aggressiveness),
        ("A8: Volatility Regime", run_a8_volatility_regime),
        ("A9: Trade Clustering", run_a9_trade_clustering),
        ("A10: Lead-Lag Analysis", run_a10_lead_lag),
        ("A11: Amihud Illiquidity", run_a11_amihud_illiquidity),
        ("A12: Order Lifespan", run_a12_order_lifespan),
    ]

    for name, func in modules:
        t0 = time.time()
        func()
        print(f"[TIMING] Module {name} finished in {time.time() - t0:.2f}s")

    print(f"\n[COMPLETE] Stage 3 DuckDB analysis finished in {time.time() - t_start:.2f}s")


if __name__ == "__main__":
    run_analysis()
