"""Publication-quality research figure generator."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from config.settings import RESULTS_DIR


def _safe_read_csv(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(file_path)
    except Exception:
        return pd.DataFrame()


def generate_all_charts() -> None:
    print("[REPORT] Generating Publication-Quality Research Figures...")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams.update({"font.family": "serif", "font.size": 12})

    color_expiry = "#1f77b4"
    color_control = "#7f7f7f"

    results_path = Path(RESULTS_DIR)

    # 1. Figure 1: VWAP Trajectory Multi-Panel (A1)
    df1 = _safe_read_csv(results_path / "a1_vwap_trajectory.csv")
    if not df1.empty and "time_bucket" in df1.columns and "basis_bps" in df1.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.lineplot(data=df1, x="time_bucket", y="basis_bps", hue="is_expiry",
                     palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 1: 1-Minute Basis Trajectory (Expiry vs Control)")
        ax.set_ylabel("Basis (bps)")
        ax.set_xlabel("Time Bucket (Settlement Window)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        fig.savefig(results_path / "fig1_vwap_basis_trajectory.png", dpi=300)
        plt.close(fig)

    # 2. Figure 2: Basis Volatility Boxplot (A2)
    df2 = _safe_read_csv(results_path / "a2_basis_divergence.csv")
    if not df2.empty and "liquidity_group" in df2.columns and "basis_std_dev" in df2.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.boxplot(data=df2, x="liquidity_group", y="basis_std_dev", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 2: Basis Volatility by Stock Liquidity Group")
        ax.set_ylabel("Basis Standard Deviation (bps)")
        plt.tight_layout()
        fig.savefig(results_path / "fig2_basis_volatility_boxplot.png", dpi=300)
        plt.close(fig)

    # 3. Figure 3: Participant Profile Breakdown (A3)
    df3 = _safe_read_csv(results_path / "a3_participant_profile.csv")
    if not df3.empty and "participant_type" in df3.columns and "volume" in df3.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=df3, x="participant_type", y="volume", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 3: Settlement Volume by Participant Identity")
        ax.set_ylabel("Total Volume (Shares)")
        plt.tight_layout()
        fig.savefig(results_path / "fig3_participant_profile.png", dpi=300)
        plt.close(fig)

    # 4. Figure 4: Algo Segmentation & IOC Rates (A4)
    df4 = _safe_read_csv(results_path / "a4_algo_segmentation.csv")
    if not df4.empty and "algo_type" in df4.columns and "ioc_rate" in df4.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.barplot(data=df4, x="algo_type", y="ioc_rate", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 4: IOC Order Submission Rate by Algo Classification")
        ax.set_ylabel("IOC Rate")
        plt.tight_layout()
        fig.savefig(results_path / "fig4_algo_ioc_rate.png", dpi=300)
        plt.close(fig)

    # 5. Figure 5: Cancellation Ratios (A5)
    df5 = _safe_read_csv(results_path / "a5_cancellation_patterns.csv")
    if not df5.empty and "time_bucket" in df5.columns and "cancel_to_entry_ratio" in df5.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.lineplot(data=df5, x="time_bucket", y="cancel_to_entry_ratio", hue="is_expiry",
                     palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 5: Cancel-to-Entry Ratio Timeline")
        ax.set_ylabel("Cancel / Entry Ratio")
        plt.xticks(rotation=45)
        plt.tight_layout()
        fig.savefig(results_path / "fig5_cancellation_ratio_timeline.png", dpi=300)
        plt.close(fig)

    # 6. Figure 6: Iceberg Hidden Volume (A6)
    df6 = _safe_read_csv(results_path / "a6_iceberg_detection.csv")
    if not df6.empty and "liquidity_group" in df6.columns and "hidden_volume_ratio" in df6.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.boxplot(data=df6, x="liquidity_group", y="hidden_volume_ratio", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 6: Hidden Iceberg Volume Ratio")
        ax.set_ylabel("Hidden Volume / Total Volume")
        plt.tight_layout()
        fig.savefig(results_path / "fig6_iceberg_hidden_volume.png", dpi=300)
        plt.close(fig)

    # 7. Figure 7: Spread Dynamics (B1)
    df7 = _safe_read_csv(results_path / "b1_spread_dynamics.csv")
    if not df7.empty and "liquidity_group" in df7.columns and "mean_spread_bps" in df7.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.boxplot(data=df7, x="liquidity_group", y="mean_spread_bps", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 7: Bid-Ask Spread Dynamics")
        ax.set_ylabel("Mean Spread (bps)")
        plt.tight_layout()
        fig.savefig(results_path / "fig7_spread_dynamics.png", dpi=300)
        plt.close(fig)

    # 8. Figure 8: Order Flow Imbalance OFI (B3)
    df8 = _safe_read_csv(results_path / "b3_order_flow_imbalance.csv")
    if not df8.empty and "time_bucket" in df8.columns and "cash_ofi" in df8.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=df8, x="time_bucket", y="cash_ofi", hue="is_expiry",
                    palette={True: color_expiry, False: color_control}, ax=ax)
        ax.set_title("Figure 8: Order Flow Imbalance (OFI) Timeline")
        ax.set_ylabel("Net Order Flow Imbalance")
        plt.xticks(rotation=45)
        plt.tight_layout()
        fig.savefig(results_path / "fig8_order_flow_imbalance.png", dpi=300)
        plt.close(fig)

    # 9. Figure 9: Price Impact & Kyle's Lambda (B4)
    df9 = _safe_read_csv(results_path / "b4_price_impact.csv")
    if not df9.empty and "is_expiry" in df9.columns and "median_price_impact_bps" in df9.columns:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.boxplot(data=df9, x="is_expiry", y="median_price_impact_bps", palette=[color_control, color_expiry], ax=ax)
        ax.set_title("Figure 9: Per-Trade Midpoint Price Impact (bps)")
        ax.set_xticklabels(["Control Day", "Expiry Day"])
        plt.tight_layout()
        fig.savefig(results_path / "fig9_price_impact_bps.png", dpi=300)
        plt.close(fig)

    # 10. Figure 10: Hypothesis Forest Plot (Stage 7 Summary)
    df_stat = _safe_read_csv(results_path / "hypothesis_testing_summary.csv")
    if not df_stat.empty and "effect_size_cohen_d" in df_stat.columns:
        fig, ax = plt.subplots(figsize=(12, 10))
        y_pos = np.arange(len(df_stat))
        ax.errorbar(df_stat["effect_size_cohen_d"], y_pos, xerr=0.15, fmt='o', color=color_expiry, ecolor='gray', elinewidth=2, capsize=4)
        ax.set_yticks(y_pos)
        ax.set_yticklabels([f"{hid}: {str(desc)[:35]}..." for hid, desc in zip(df_stat["hypothesis_id"], df_stat["description"])])
        ax.axvline(0, color='red', linestyle='--')
        ax.set_xlabel("Effect Size (Cohen's d)")
        ax.set_title("Figure 10: Hypothesis Testing Forest Plot (H1-H30 Effect Sizes)")
        ax.invert_yaxis()
        plt.tight_layout()
        fig.savefig(results_path / "fig10_hypothesis_forest_plot.png", dpi=300)
        plt.close(fig)

    print(f"[DONE] Generated publication figures in {RESULTS_DIR}")


if __name__ == "__main__":
    generate_all_charts()
