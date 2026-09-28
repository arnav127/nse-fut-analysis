"""The 2022 trading calendar, and what kind of day each session is.

The matched design compares each monthly expiry with one control session. That controls for
the month and not for the day, and the day is exactly what is in question: a monthly expiry
is also a Thursday on which the index options expire, and it falls in the last days of the
month. The full-year tape lets each of those be separated from the stock derivatives
settlement by comparing the monthly expiry against days that share one feature and not the
other.

    monthly_expiry   stock futures and options settle on this session's closing VWAP; the
                     index options expire too
    weekly_expiry    index options expire, stock derivatives do not
    month_end        the last session of the month, when it is not itself an expiry
    normal           everything else

The trading days are the sessions for which the exchange published a cash trade file, so the
calendar needs no holiday list typed in by hand.
"""

from __future__ import annotations

import glob
from datetime import date
from pathlib import Path
from typing import Dict, List

from config.settings import EXPIRY_THURSDAYS_DDMMYYYY, RAW_DATA_DIR
from utils.paths import SESSION_FMT, session_to_date

YEAR = 2022

DAY_TYPES = ("monthly_expiry", "weekly_expiry", "month_end", "normal")

DAY_TYPE_LABELS = {
    "monthly_expiry": "Monthly expiry",
    "weekly_expiry": "Weekly index expiry",
    "month_end": "Month end",
    "normal": "Other sessions",
}


def trading_sessions(raw_dir: Path = Path(RAW_DATA_DIR)) -> List[str]:
    """Every 2022 session with a cash trade file, in date order."""
    sessions = set()
    for path in glob.glob((raw_dir / "CASH_Trades_*.DAT.gz").as_posix()):
        stem = Path(path).name.split("_")[2].split(".")[0]
        if len(stem) == 8 and stem.isdigit() and stem.endswith(str(YEAR)):
            sessions.add(stem)
    return sorted(sessions, key=session_to_date)


def classify(sessions: List[str]) -> Dict[str, str]:
    """Day type for each session.

    A weekly expiry falls on Thursday, or on the preceding session when the Thursday is a
    holiday. The exchange moves the expiry earlier, never later, so the rule is to take the
    last session of each Monday-to-Thursday span.
    """
    dates = {s: session_to_date(s) for s in sessions}
    monthly = set(EXPIRY_THURSDAYS_DDMMYYYY)

    weekly = set()
    by_week: Dict[tuple, List[str]] = {}
    for session, day in dates.items():
        if day.weekday() <= 3:  # Monday..Thursday
            by_week.setdefault(tuple(day.isocalendar()[:2]), []).append(session)
    for members in by_week.values():
        last = max(members, key=lambda s: dates[s])
        weekly.add(last)

    month_end = {}
    for session, day in dates.items():
        key = (day.year, day.month)
        if key not in month_end or day > dates[month_end[key]]:
            month_end[key] = session
    month_end_set = set(month_end.values())

    kinds = {}
    for session in sessions:
        if session in monthly:
            kinds[session] = "monthly_expiry"
        elif session in weekly:
            kinds[session] = "weekly_expiry"
        elif session in month_end_set:
            kinds[session] = "month_end"
        else:
            kinds[session] = "normal"
    return kinds


def next_session(sessions: List[str]) -> Dict[str, str]:
    """The following trading session for each session, where there is one."""
    ordered = sorted(sessions, key=session_to_date)
    return {a: b for a, b in zip(ordered, ordered[1:])}


def iso(session: str) -> str:
    return session_to_date(session).isoformat()


def from_date(day: date) -> str:
    return day.strftime(SESSION_FMT)
