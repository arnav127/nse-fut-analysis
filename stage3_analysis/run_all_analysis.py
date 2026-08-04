"""Orchestrator for Stage 3 trade-level analysis modules (A1-A12)."""

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
    run_a1_vwap_trajectory()
    run_a2_basis_divergence()
    run_a3_participant_profile()
    run_a4_algo_segmentation()
    run_a5_cancellation_patterns()
    run_a6_iceberg_detection()
    run_a7_ioc_aggressiveness()
    run_a8_volatility_regime()
    run_a9_trade_clustering()
    run_a10_lead_lag()
    run_a11_amihud_illiquidity()
    run_a12_order_lifespan()
    print("\n[COMPLETE] Stage 3 DuckDB analysis finished.")


if __name__ == "__main__":
    run_analysis()
