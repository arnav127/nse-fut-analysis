"""
generate_charts.py — Publication-quality chart generation for Stage 3, 5, 6 results.
"""
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from config.settings import RESULTS_DIR

def generate_all_charts():
    print("[REPORT] Generating Publication-Quality Figures...")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams.update({"font.family": "serif", "font.size": 12})

    # 1. VWAP Trajectory & Basis Plot (A1)
    a1_path = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    if os.path.exists(a1_path):
        df_a1 = pd.read_csv(a1_path)
        if not df_a1.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.lineplot(data=df_a1, x="time_bucket", y="basis_bps", hue="is_expiry", ax=ax)
            ax.set_title("1-Minute Basis Trajectory (Expiry vs Control)")
            ax.set_ylabel("Basis (bps)")
            ax.set_xlabel("Time Bucket")
            plt.xticks(rotation=45)
            plt.tight_layout()
            out_png = os.path.join(RESULTS_DIR, "fig_vwap_basis_trajectory.png")
            fig.savefig(out_png, dpi=300)
            plt.close(fig)

    # 2. Spread Dynamics Plot (B1)
    b1_path = os.path.join(RESULTS_DIR, "b1_spread_dynamics.csv")
    if os.path.exists(b1_path):
        df_b1 = pd.read_csv(b1_path)
        if not df_b1.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.boxplot(data=df_b1, x="liquidity_group", y="mean_spread_bps", hue="is_expiry", ax=ax)
            ax.set_title("Bid-Ask Spread Dynamics by Liquidity Group")
            ax.set_ylabel("Mean Spread (bps)")
            plt.tight_layout()
            out_png = os.path.join(RESULTS_DIR, "fig_spread_dynamics.png")
            fig.savefig(out_png, dpi=300)
            plt.close(fig)

    print("[DONE] Charts generated successfully.")
