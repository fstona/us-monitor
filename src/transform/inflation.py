"""Inflation decomposition (Powell's three buckets)."""
from __future__ import annotations

import pandas as pd

from src import config
from src.transform.indicators import yoy


def core_cpi_contributions(core: pd.Series, goods: pd.Series, shelter: pd.Series,
                           weights: dict[str, float] = config.CPI_CORE_WEIGHTS) -> pd.DataFrame:
    """Core CPI (y/y) split into core goods, shelter and supercore contributions.

    Goods and shelter use their approximate share of core; supercore is the
    residual, so the three columns sum exactly to core CPI y/y. Inputs are
    price-index levels (monthly).
    """
    core_yoy = yoy(core, 12)
    contrib = pd.DataFrame({
        "Core goods": weights["goods"] * yoy(goods, 12),
        "Shelter": weights["shelter"] * yoy(shelter, 12),
    })
    contrib["Supercore (services ex-shelter)"] = core_yoy - contrib.sum(axis=1)
    return contrib.dropna()
