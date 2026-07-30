"""
load_bloomberg_data.py — Read exported Bloomberg CSVs into DataFrames.
"""
import os
import pandas as pd
from config.settings import BLOOMBERG_DATA_DIR

def load_calendar_spreads():
    p = os.path.join(BLOOMBERG_DATA_DIR, "calendar_spreads.csv")
    return pd.read_csv(p, parse_dates=["date"]) if os.path.exists(p) else pd.DataFrame()

def load_open_interest():
    p = os.path.join(BLOOMBERG_DATA_DIR, "open_interest.csv")
    return pd.read_csv(p, parse_dates=["date"]) if os.path.exists(p) else pd.DataFrame()

def load_cost_of_carry():
    p = os.path.join(BLOOMBERG_DATA_DIR, "cost_of_carry.csv")
    return pd.read_csv(p, parse_dates=["date"]) if os.path.exists(p) else pd.DataFrame()

def load_futures_volume():
    p = os.path.join(BLOOMBERG_DATA_DIR, "futures_volume.csv")
    return pd.read_csv(p, parse_dates=["date"]) if os.path.exists(p) else pd.DataFrame()

def build_bloomberg_master():
    spreads = load_calendar_spreads()
    oi = load_open_interest()
    coc = load_cost_of_carry()
    vol = load_futures_volume()

    if spreads.empty:
        return pd.DataFrame()

    m = spreads.merge(oi, on=["date", "symbol"], how="outer") if not oi.empty else spreads
    m = m.merge(coc, on=["date", "symbol"], how="outer") if not coc.empty else m
    m = m.merge(vol, on=["date", "symbol"], how="outer") if not vol.empty else m
    return m
