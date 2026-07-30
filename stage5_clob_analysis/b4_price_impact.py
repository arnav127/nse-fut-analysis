"""
b4_price_impact.py — Per-trade price impact analysis & Kyle's Lambda estimation (H17).
"""
import os
import glob
import pandas as pd
import numpy as np
from scipy import stats
from config.settings import CLOB_DATA_DIR, ENRICHED_DATA_DIR, RESULTS_DIR, EXPIRY_THURSDAYS_DDMMYYYY

def run_b4_price_impact():
    print("[ANALYSIS B4] Calculating Per-Trade Price Impact & Kyle's Lambda...")
    
    clob_files = glob.glob(os.path.join(CLOB_DATA_DIR, "*", "date=*", "snapshots.parquet"))
    out_csv = os.path.join(RESULTS_DIR, "b4_price_impact.csv")

    if not clob_files:
        print("[WARN] No CLOB snapshot files found for B4 analysis.")
        df_res = pd.DataFrame(columns=[
            "symbol", "trade_date", "is_expiry", "mean_price_impact_bps",
            "median_price_impact_bps", "kyle_lambda", "kyle_r2"
        ])
        df_res.to_csv(out_csv, index=False)
        return df_res

    results = []

    for f in clob_files:
        try:
            df_snap = pd.read_parquet(f)
        except Exception:
            continue

        if df_snap.empty or "midpoint" not in df_snap.columns:
            continue

        symbol = df_snap["symbol"].iloc[0]
        trade_date = df_snap["trade_date"].iloc[0]
        date_clean = pd.to_datetime(trade_date).strftime("%d%m%Y")
        is_expiry = date_clean in EXPIRY_THURSDAYS_DDMMYYYY

        # Load enriched trades for this symbol and date
        trades_path = os.path.join(ENRICHED_DATA_DIR, "cash_trades")
        try:
            df_trades = pd.read_parquet(
                trades_path,
                filters=[("symbol", "==", symbol), ("is_settlement_window", "==", True)]
            )
            df_trades = df_trades[df_trades["trade_date"] == trade_date]
        except Exception:
            df_trades = pd.DataFrame()

        if df_trades.empty:
            continue

        # Sort trades by timestamp
        df_trades = df_trades.sort_values("txn_time_jiffies")

        # 1. Price Impact per trade: midpoint displacement
        impacts_bps = []
        signed_flows = []
        midpoint_changes = []

        # Convert timestamps for matching
        df_snap["time_sec"] = pd.to_datetime(df_snap["timestamp"]).dt.floor("s")
        df_trades["time_sec"] = pd.to_datetime(df_trades["txn_datetime"]).dt.floor("s")

        snap_map = df_snap.set_index("time_sec")["midpoint"].to_dict()

        for _, tr in df_trades.iterrows():
            t_sec = tr["time_sec"]
            prev_sec = t_sec - pd.Timedelta(seconds=1)
            next_sec = t_sec + pd.Timedelta(seconds=1)

            p_before = snap_map.get(prev_sec, snap_map.get(t_sec, None))
            p_after = snap_map.get(next_sec, snap_map.get(t_sec, None))

            if p_before and p_after and p_before > 0:
                # Signed trade side: +1 if trade at/above midpoint, -1 otherwise
                side = 1.0 if tr["trade_price"] >= p_before else -1.0
                impact = ((p_after - p_before) / p_before) * 10000.0 * side
                impacts_bps.append(impact)

                signed_flows.append(side * tr["trade_quantity"])
                midpoint_changes.append((p_after - p_before) / p_before * 10000.0)

        # 2. Estimate Kyle's Lambda via OLS regression: midpoint_change = lambda * signed_order_flow
        kyle_lambda = 0.0
        kyle_r2 = 0.0
        if len(signed_flows) > 5:
            slope, intercept, r_value, p_value, std_err = stats.linregress(signed_flows, midpoint_changes)
            kyle_lambda = slope
            kyle_r2 = r_value ** 2

        if impacts_bps:
            results.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "is_expiry": is_expiry,
                "mean_price_impact_bps": np.mean(impacts_bps),
                "median_price_impact_bps": np.median(impacts_bps),
                "std_price_impact_bps": np.std(impacts_bps),
                "kyle_lambda": kyle_lambda,
                "kyle_r2": kyle_r2,
                "n_trades": len(impacts_bps)
            })

    df_res = pd.DataFrame(results)
    df_res.to_csv(out_csv, index=False)
    print(f"[DONE] Saved B4 Price Impact & Kyle's Lambda results to {out_csv}")
    return df_res
