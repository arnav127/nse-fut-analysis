"""Bloomberg Terminal CSV loader and dataset consolidation utility."""

from pathlib import Path

import pandas as pd

from config.settings import BLOOMBERG_DATA_DIR


def load_calendar_spreads() -> pd.DataFrame:
    p = Path(BLOOMBERG_DATA_DIR) / "calendar_spreads.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


def load_open_interest() -> pd.DataFrame:
    p = Path(BLOOMBERG_DATA_DIR) / "open_interest.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


def load_cost_of_carry() -> pd.DataFrame:
    p = Path(BLOOMBERG_DATA_DIR) / "cost_of_carry.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


def load_futures_volume() -> pd.DataFrame:
    p = Path(BLOOMBERG_DATA_DIR) / "futures_volume.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else pd.DataFrame()


def build_bloomberg_master() -> pd.DataFrame:
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
