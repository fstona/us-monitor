"""Rates: policy stance, market-implied direction and the Treasury curve."""
from __future__ import annotations

import pandas as pd

# Curve tenors (FRED constant-maturity IDs), in maturity order.
CURVE_TENORS: dict[str, str] = {"3m": "DGS3MO", "2y": "DGS2", "5y": "DGS5",
                                "10y": "DGS10", "30y": "DGS30"}


def target_midpoint(upper: pd.Series, lower: pd.Series) -> pd.Series:
    """Daily midpoint of the fed funds target range (range regime, Dec-2008+)."""
    return ((upper + lower) / 2).dropna()


def real_policy_rate(nominal: pd.Series, inflation: pd.Series) -> pd.Series:
    """Ex-post real policy rate: monthly nominal rate minus an inflation gauge.

    Compare against r* — above r* = restrictive stance, below = accommodative.
    """
    df = pd.DataFrame({"i": nominal, "pi": inflation}).dropna()
    return df["i"] - df["pi"]


def market_implied_direction(two_year: pd.Series, policy_mid: pd.Series) -> pd.Series:
    """2y Treasury minus the funds target midpoint (daily).

    A quick read of what markets price for the next ~2 years before a proper
    futures-based path exists: clearly negative = cuts priced, positive = hikes.
    It also embeds a (small) term premium, so read it directionally.
    """
    mid = policy_mid.reindex(two_year.index, method="ffill")
    return (two_year - mid).dropna()


def curve_snapshot(tenors: dict[str, pd.Series],
                   lags: dict[str, pd.DateOffset]) -> pd.DataFrame:
    """Yield-curve cross-sections: rows = tenor, columns = 'Latest' + each lag."""
    out = {}
    last_date = min(s.dropna().index[-1] for s in tenors.values())
    for name, off in {"Latest": pd.DateOffset(0), **lags}.items():
        when = last_date - off
        out[f"{name} ({when:%d %b %Y})"] = {t: float(s.dropna().asof(when)) for t, s in tenors.items()}
    return pd.DataFrame(out)
