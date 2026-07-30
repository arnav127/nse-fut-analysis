"""
generate_report.py — Final research report generator compiling findings across all stages.
"""
import os
import pandas as pd
from config.settings import RESULTS_DIR
from stage7_report.stat_tests import run_all_hypothesis_tests
from stage7_report.generate_charts import generate_all_charts

def generate_report():
    print("\n=== STAGE 7: CONSOLIDATED REPORT GENERATION ===")

    summary_df = run_all_hypothesis_tests()
    generate_all_charts()

    report_md = os.path.join(RESULTS_DIR, "final_research_report.md")

    with open(report_md, "w") as f:
        f.write("# Expiry Day Dynamics & VWAP Settlement Anomalies — Research Report\n\n")
        f.write("## Executive Summary\n\n")
        f.write("This report presents empirical analysis of tick-level order and trade data on the National Stock Exchange (NSE) ")
        f.write("for 2022 monthly expiry Thursdays and control days. We examine VWAP trajectory, market participant behavior, ")
        f.write("CLOB liquidity erosion, and Bloomberg-derived roll pressure.\n\n")

        f.write("## Hypothesis Testing Summary\n\n")
        f.write(summary_df.to_markdown(index=False))
        f.write("\n\n")

        f.write("## Visual Artifacts\n\n")
        f.write("- ![VWAP Trajectory](fig_vwap_basis_trajectory.png)\n")
        f.write("- ![Spread Dynamics](fig_spread_dynamics.png)\n")

    print(f"[DONE] Final research report compiled at {report_md}")

if __name__ == "__main__":
    generate_report()
