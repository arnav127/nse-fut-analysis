"""
run_bloomberg_analysis.py — Orchestrator for Stage 6 Bloomberg-integrated analysis modules.
"""
from stage6_bloomberg.c1_roll_pressure import run_c1_roll_pressure
from stage6_bloomberg.c2_cost_of_carry import run_c2_cost_of_carry
from stage6_bloomberg.c3_directional_validation import run_c3_directional_validation

def run_bloomberg():
    print("\n=== STAGE 6: BLOOMBERG INTEGRATED ANALYSIS ===")
    run_c1_roll_pressure()
    run_c2_cost_of_carry()
    run_c3_directional_validation()
    print("\n[COMPLETE] Stage 6 Bloomberg analysis finished.")

if __name__ == "__main__":
    run_bloomberg()
