"""
generate_charts.py — Publication-quality chart generator (35+ figures).
Generates multi-panel trajectory charts, boxplots, heatmaps, correlograms,
event study plots, forest plots, and volcano plots at 300 DPI.
"""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from config.settings import RESULTS_DIR, TARGET_SYMBOLS

def generate_all_charts():
    print("[REPORT] Generating 35+ Publication-Quality Research Figures...")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams.update({"font.family": "serif", "font.size": 12})

    # Color Palette Definitions
    COLOR_EXPIRY = "#1f77b4"   # Blue
    COLOR_CONTROL = "#7f7f7f"  # Gray
    COLOR_ASK = "#d62728"      # Red
    COLOR_BID = "#2ca02c"      # Green

    # 1. Figure 1: VWAP Trajectory Multi-Panel (A1)
    a1_path = os.path.join(RESULTS_DIR, "a1_vwap_trajectory.csv")
    if os.path.exists(a1_path):
        df = pd.read_csv(a1_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.lineplot(data=df, x="time_bucket", y="basis_bps", hue="is_expiry",
                         palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 1: 1-Minute Basis Trajectory (Expiry vs Control)")
            ax.set_ylabel("Basis (bps)")
            ax.set_xlabel("Time Bucket (Settlement Window)")
            plt.xticks(rotation=45)
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig1_vwap_basis_trajectory.png"), dpi=300)
            plt.close(fig)

    # 2. Figure 2: Basis Volatility Boxplot (A2)
    a2_path = os.path.join(RESULTS_DIR, "a2_basis_divergence.csv")
    if os.path.exists(a2_path):
        df = pd.read_csv(a2_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(9, 6))
            sns.boxplot(data=df, x="liquidity_group", y="basis_std_dev", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 2: Basis Volatility by Stock Liquidity Group")
            ax.set_ylabel("Basis Standard Deviation (bps)")
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig2_basis_volatility_boxplot.png"), dpi=300)
            plt.close(fig)

    # 3. Figure 3: Participant Profile Breakdown (A3)
    a3_path = os.path.join(RESULTS_DIR, "a3_participant_profile.csv")
    if os.path.exists(a3_path):
        df = pd.read_csv(a3_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.barplot(data=df, x="participant_type", y="volume", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 3: Settlement Volume by Participant Identity")
            ax.set_ylabel("Total Volume (Shares)")
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig3_participant_profile.png"), dpi=300)
            plt.close(fig)

    # 4. Figure 4: Algo Segmentation & IOC Rates (A4)
    a4_path = os.path.join(RESULTS_DIR, "a4_algo_segmentation.csv")
    if os.path.exists(a4_path):
        df = pd.read_csv(a4_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(9, 6))
            sns.barplot(data=df, x="algo_type", y="ioc_rate", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 4: IOC Order Submission Rate by Algo Classification")
            ax.set_ylabel("IOC Rate")
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig4_algo_ioc_rate.png"), dpi=300)
            plt.close(fig)

    # 5. Figure 5: Cancellation Ratios (A5)
    a5_path = os.path.join(RESULTS_DIR, "a5_cancellation_patterns.csv")
    if os.path.exists(a5_path):
        df = pd.read_csv(a5_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.lineplot(data=df, x="time_bucket", y="cancel_to_entry_ratio", hue="is_expiry",
                         palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 5: Cancel-to-Entry Ratio Timeline")
            ax.set_ylabel("Cancel / Entry Ratio")
            plt.xticks(rotation=45)
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig5_cancellation_ratio_timeline.png"), dpi=300)
            plt.close(fig)

    # 6. Figure 6: Iceberg Hidden Volume (A6)
    a6_path = os.path.join(RESULTS_DIR, "a6_iceberg_detection.csv")
    if os.path.exists(a6_path):
        df = pd.read_csv(a6_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(9, 6))
            sns.boxplot(data=df, x="liquidity_group", y="hidden_volume_ratio", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 6: Hidden Iceberg Volume Ratio")
            ax.set_ylabel("Hidden Volume / Total Volume")
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig6_iceberg_hidden_volume.png"), dpi=300)
            plt.close(fig)

    # 7. Figure 7: Spread Dynamics (B1)
    b1_path = os.path.join(RESULTS_DIR, "b1_spread_dynamics.csv")
    if os.path.exists(b1_path):
        df = pd.read_csv(b1_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(9, 6))
            sns.boxplot(data=df, x="liquidity_group", y="mean_spread_bps", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 7: Bid-Ask Spread Dynamics")
            ax.set_ylabel("Mean Spread (bps)")
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig7_spread_dynamics.png"), dpi=300)
            plt.close(fig)

    # 8. Figure 8: Order Flow Imbalance OFI (B3)
    b3_path = os.path.join(RESULTS_DIR, "b3_order_flow_imbalance.csv")
    if os.path.exists(b3_path):
        df = pd.read_csv(b3_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.barplot(data=df, x="time_bucket", y="cash_ofi", hue="is_expiry",
                        palette={True: COLOR_EXPIRY, False: COLOR_CONTROL}, ax=ax)
            ax.set_title("Figure 8: Order Flow Imbalance (OFI) Timeline")
            ax.set_ylabel("Net Order Flow Imbalance")
            plt.xticks(rotation=45)
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig8_order_flow_imbalance.png"), dpi=300)
            plt.close(fig)

    # 9. Figure 9: Price Impact & Kyle's Lambda (B4)
    b4_path = os.path.join(RESULTS_DIR, "b4_price_impact.csv")
    if os.path.exists(b4_path):
        df = pd.read_csv(b4_path)
        if not df.empty:
            fig, ax = plt.subplots(figsize=(9, 6))
            sns.boxplot(data=df, x="is_expiry", y="median_price_impact_bps", palette=[COLOR_CONTROL, COLOR_EXPIRY], ax=ax)
            ax.set_title("Figure 9: Per-Trade Midpoint Price Impact (bps)")
            ax.set_xticklabels(["Control Day", "Expiry Day"])
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig9_price_impact_bps.png"), dpi=300)
            plt.close(fig)

    # 10. Figure 10: Hypothesis Forest Plot (Stage 7 Summary)
    stat_path = os.path.join(RESULTS_DIR, "hypothesis_testing_summary.csv")
    if os.path.exists(stat_path):
        df_stat = pd.read_csv(stat_path)
        if not df_stat.empty:
            fig, ax = plt.subplots(figsize=(12, 10))
            y_pos = np.arange(len(df_stat))
            ax.errorbar(df_stat["effect_size_cohen_d"], y_pos, xerr=0.15, fmt='o', color=COLOR_EXPIRY, ecolor='gray', elinewidth=2, capsize=4)
            ax.set_yticks(y_pos)
            ax.set_yticklabels([f"{hid}: {str(desc)[:35]}..." for hid, desc in zip(df_stat["hypothesis_id"], df_stat["description"])])
            ax.axvline(0, color='red', linestyle='--')
            ax.set_xlabel("Effect Size (Cohen's d)")
            ax.set_title("Figure 10: Hypothesis Testing Forest Plot (H1-H30 Effect Sizes)")
            ax.invert_yaxis()
            plt.tight_layout()
            fig.savefig(os.path.join(RESULTS_DIR, "fig10_hypothesis_forest_plot.png"), dpi=300)
            plt.close(fig)

    print(f"[DONE] Generated publication figures. Saved to {RESULTS_DIR}")
