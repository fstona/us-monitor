"""Labor-market relationships (Michaillat–Saez framework).

Builds the integrated labor indicators rather than raw series:

  tightness  θ = v / u                (vacancies per unemployed; 1.0 = full employment)
  FERU       u* = sqrt(u · v)         (full-employment rate of unemployment)
  gap        u − u*                   (unemployment gap; >0 = slack, <0 = overheating)

where u is the unemployment rate (%) and v the vacancy rate (% of the labor
force). Vacancy data (JOLTS) starts in 2000, so the frame begins there.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import data


INPUTS = ["UNRATE", "UNEMPLOY", "CLF16OV", "JTSJOL"]


def labor_market_frame() -> pd.DataFrame:
    u = data.get_series("UNRATE")              # %
    unemployed = data.get_series("UNEMPLOY")   # thousands
    labor_force = data.get_series("CLF16OV")   # thousands
    vacancies = data.get_series("JTSJOL")      # thousands

    df = pd.DataFrame({"u": u}).copy()
    df["v"] = vacancies / labor_force * 100.0  # vacancy rate, % of labor force
    df["tightness"] = vacancies / unemployed   # v/u ratio (labor force cancels)
    df["feru"] = np.sqrt(df["u"] * df["v"])     # full-employment unemployment rate
    df["gap"] = df["u"] - df["feru"]            # unemployment gap
    return df.dropna(subset=["v"])              # restrict to the JOLTS era (2000+)
