"""FOMC structure: participants, voting rotation and communication blackout.

Voting rule (Federal Reserve Act §12A): the 7 Governors and the New York Fed
president vote every year; four rotating seats are filled by one president
from each group below, cycling annually (Cleveland/Chicago alternate). The
lists are ordered starting at ``ROTATION_BASE_YEAR``, so any year resolves
without manual updates. Interim presidents (first vice presidents acting as
president) vote when their bank's seat comes up.

Blackout (FOMC external communications policy): begins at midnight ET on the
second Saturday before a meeting and ends at midnight ET the day after it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config

ROSTER_PATH = config.PROJECT_ROOT / "reference" / "fomc_roster.csv"
ROTATION_BASE_YEAR = 2026
ROTATION_GROUPS: list[list[str]] = [
    ["philadelphia", "richmond", "boston"],
    ["cleveland", "chicago"],
    ["dallas", "atlanta", "st_louis"],
    ["minneapolis", "san_francisco", "kansas_city"],
]
PERMANENT_SEATS = {"board", "new_york"}


def load_roster(path: Path = ROSTER_PATH) -> pd.DataFrame:
    """Participants with the ITC hawk scale (−1 most dovish … +1 most hawkish)."""
    return pd.read_csv(path)


def is_voter(seat: str, year: int) -> bool:
    if seat in PERMANENT_SEATS:
        return True
    for group in ROTATION_GROUPS:
        if seat in group:
            return group[(year - ROTATION_BASE_YEAR) % len(group)] == seat
    raise ValueError(f"Unknown FOMC seat: {seat!r}")


def blackout_window(meeting_start: pd.Timestamp, meeting_end: pd.Timestamp
                    ) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, end] dates of the blackout around one meeting (inclusive)."""
    days_back = (meeting_start.weekday() - 5) % 7 or 7   # to the previous Saturday
    first_sat = meeting_start - pd.Timedelta(days=days_back)
    return first_sat - pd.Timedelta(days=7), meeting_end + pd.Timedelta(days=1)


def blackout_status(meetings: list[tuple[pd.Timestamp, pd.Timestamp]],
                    today: pd.Timestamp) -> dict:
    """Next meeting, its blackout window, and whether ``today`` is inside it."""
    today = pd.Timestamp(today).normalize()
    upcoming = [(s, e) for s, e in meetings if e + pd.Timedelta(days=1) >= today]
    if not upcoming:
        return {}
    start, end = min(upcoming)
    b0, b1 = blackout_window(start, end)
    return {"meeting_start": start, "meeting_end": end, "blackout_start": b0,
            "blackout_end": b1, "in_blackout": b0 <= today <= b1,
            "days_to_blackout": (b0 - today).days}
