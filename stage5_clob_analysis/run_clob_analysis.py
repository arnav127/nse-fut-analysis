"""
run_clob_analysis.py — Orchestrator for Stage 5 CLOB-based analysis modules.
"""
from stage5_clob_analysis.b1_spread_dynamics import run_b1_spread_dynamics
from stage5_clob_analysis.b2_depth_erosion import run_b2_depth_erosion
from stage5_clob_analysis.b3_order_flow_imbalance import run_b3_order_flow_imbalance
from stage5_clob_analysis.b4_price_impact import run_b4_price_impact
from stage5_clob_analysis.b5_book_asymmetry import run_b5_book_asymmetry
from utils.spark_session import get_spark

def run_clob_analysis():
    spark = get_spark("NSE_Stage5_CLOB_Analysis")
    print("\n=== STAGE 5: CLOB-BASED ANALYSIS ===")
    run_b1_spread_dynamics()
    run_b2_depth_erosion()
    run_b3_order_flow_imbalance(spark=spark)
    run_b4_price_impact()
    run_b5_book_asymmetry()
    print("\n[COMPLETE] Stage 5 CLOB analysis finished.")

if __name__ == "__main__":
    run_clob_analysis()
