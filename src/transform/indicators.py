"""Common indicator transforms applied to raw series for display."""
from __future__ import annotations

import pandas as pd

# Approximate periods-per-year by native frequency, used for annualizing.
PER_YEAR = {"D": 252, "W": 52, "M": 12, "Q": 4, "A": 1}


def yoy(s: pd.Series, periods: int = 12) -> pd.Series:
    """Year-over-year % change. ``periods`` should match the series frequency."""
    return s.pct_change(periods, fill_method=None) * 100


def mom_diff(s: pd.Series) -> pd.Series:
    """Period-over-period level change (e.g. monthly payroll gains)."""
    return s.diff()


def annualized(s: pd.Series, window: int, freq: str = "M") -> pd.Series:
    """Annualized % change over ``window`` periods (e.g. 3m/6m inflation momentum)."""
    per_year = PER_YEAR.get(freq, 12)
    return ((s / s.shift(window)) ** (per_year / window) - 1) * 100


def to_monthly(s: pd.Series, how: str = "last") -> pd.Series:
    """Collapse a daily/weekly series to month-start stamps (FRED's monthly
    convention), so it aligns with monthly macro data. ``how``: last | mean."""
    s = s.dropna()
    rs = s.resample("MS")
    return (rs.mean() if how == "mean" else rs.last()).dropna()


def rebase(s: pd.Series, start: str | pd.Timestamp, base: float = 100.0) -> pd.Series:
    """Rebase a level series to ``base`` at its first observation on/after ``start``."""
    s = s.dropna()
    s = s[s.index >= pd.Timestamp(start)]
    return s / s.iloc[0] * base if len(s) else s


def change_over(s: pd.Series, offset: pd.DateOffset, pct: bool = True) -> float | None:
    """Change from the value as of (last date - offset) to the latest value."""
    s = s.dropna()
    if s.empty:
        return None
    then = s.asof(s.index[-1] - offset)
    if pd.isna(then):
        return None
    now = s.iloc[-1]
    return float((now / then - 1) * 100) if pct else float(now - then)


def apply_transform(s: pd.Series, transform: str, freq: str = "M") -> pd.Series:
    """Dispatch a named transform (see ``config.Series.transform``)."""
    if transform == "yoy":
        return yoy(s, periods=PER_YEAR.get(freq, 12))
    if transform == "mom_diff":
        return mom_diff(s)
    if transform == "ann3m":
        return annualized(s, 3, freq)
    if transform == "ann6m":
        return annualized(s, 6, freq)
    return s  # "level"
