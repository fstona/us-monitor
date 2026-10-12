"""Fiscal position and debt dynamics.

Unit discipline (all verified on FRED):
  MTSDS133FMS   monthly surplus(+)/deficit(−), $ millions, NOT annualized
  FYGFDPUN      debt held by the public, $ millions, quarterly (end of period)
  A091RC1Q027SBEA, FGRECPT, GDP   $ billions, quarterly SAAR
"""
from __future__ import annotations

import pandas as pd


def _monthly_gdp(gdp_bn_saar: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Quarterly nominal GDP (SAAR) carried onto a monthly grid."""
    return gdp_bn_saar.reindex(gdp_bn_saar.index.union(index)).ffill().reindex(index)


def balance_12m_pct_gdp(monthly_balance_mn: pd.Series, gdp_bn_saar: pd.Series) -> pd.Series:
    """Rolling 12-month federal balance as % of GDP (negative = deficit)."""
    rolling_bn = monthly_balance_mn.rolling(12).sum() / 1e3
    gdp = _monthly_gdp(gdp_bn_saar, rolling_bn.index)
    return (rolling_bn / gdp * 100).dropna()


def ratio_pct(numerator_bn: pd.Series, gdp_bn_saar: pd.Series) -> pd.Series:
    """Quarterly flow/stock in $bn as % of nominal GDP."""
    return (numerator_bn / gdp_bn_saar * 100).dropna()


def effective_interest_rate(interest_bn_saar: pd.Series, debt_public_mn: pd.Series) -> pd.Series:
    """Average interest rate on federal debt: interest paid / avg debt held by public.

    Compare against nominal GDP growth (r − g): r > g means debt/GDP rises
    even with a balanced primary budget.
    """
    debt_bn = debt_public_mn / 1e3
    avg_debt = (debt_bn + debt_bn.shift(1)) / 2
    return (interest_bn_saar / avg_debt * 100).dropna()
