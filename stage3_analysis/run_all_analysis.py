"""
run_all_analysis.py — Orchestrator for Stage 3 trade-level analysis modules.
"""
from stage3_analysis.a1_vwap_trajectory import run_a1_vwap_trajectory
from stage3_analysis.a2_basis_divergence import run_a2_basis_divergence
from stage3_analysis.a3_participant_profile import run_a3_participant_profile
from stage3_analysis.a4_algo_segmentation import run_a4_algo_segmentation
from stage3_analysis.a5_cancellation_patterns import run_a5_cancellation_patterns
from stage3_analysis.a6_iceberg_detection import run_a6_iceberg_detection
from stage3_analysis.a7_ioc_aggressiveness import run_a7_ioc_aggressiveness
from utils.spark_session import get_spark

def run_analysis():
    spark = get_spark("NSE_Stage3_Analysis")
    print("\n=== STAGE 3: TRADE-LEVEL ANALYSIS ===")
    run_a1_vwap_trajectory(spark=spark)
    run_a2_basis_divergence()
    run_a3_participant_profile(spark=spark)
    run_a4_algo_segmentation(spark=spark)
    run_a5_cancellation_patterns(spark=spark)
    run_a6_iceberg_detection(spark=spark)
    run_a7_ioc_aggressiveness(spark=spark)
    print("\n[COMPLETE] Stage 3 analysis finished.")

if __name__ == "__main__":
    run_analysis()
