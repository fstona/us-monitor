"""Monetary policy rules.

Implements the Taylor (1993) rule, the balanced-approach rule (Yellen, 2017)
and an inertial variant. All rules take the *activity gap expressed in output-
gap percentage points*; use :func:`unemployment_to_output_gap` to convert an
unemployment gap via Okun's law, or :func:`output_gap` for a direct GDP gap.

    Taylor (1993):        i = r* + pi + 0.5 (pi - pi*) + 0.5 * gap
    Balanced approach:    i = r* + pi + 0.5 (pi - pi*) + 1.0 * gap
    Inertial:             i_t = rho * i_{t-1} + (1 - rho) * i_prescribed

where pi is current inflation (default Core PCE, y/y), pi* the 2% target,
r* the neutral real rate, and gap the output gap (%, positive = above
potential).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import config


def output_gap(real_gdp: float, potential_gdp: float) -> float:
    """Output gap in % of potential (positive = economy above potential)."""
    return (real_gdp / potential_gdp - 1.0) * 100.0


def unemployment_to_output_gap(unrate: float, u_star: float, okun: float = config.OKUN_COEF) -> float:
    """Convert an unemployment gap to an output-gap equivalent via Okun's law.

    Unemployment above its natural rate (u_star) implies a negative output gap.
    """
    return -okun * (unrate - u_star)


def taylor(
    inflation: float,
    gap: float,
    r_star: float = config.DEFAULT_R_STAR,
    target: float = config.INFLATION_TARGET,
    inflation_coef: float = 0.5,
    gap_coef: float = 0.5,
) -> float:
    """Prescribed nominal policy rate (%) for a Taylor-type rule."""
    return r_star + inflation + inflation_coef * (inflation - target) + gap_coef * gap


def balanced_approach(inflation: float, gap: float, **kwargs) -> float:
    """Balanced-approach rule: doubles the activity-gap response to 1.0."""
    return taylor(inflation, gap, gap_coef=1.0, **kwargs)


def inertial(prescribed: float, prev_rate: float, rho: float = config.DEFAULT_RHO) -> float:
    """Smooth a prescribed rate toward the previous policy rate."""
    return rho * prev_rate + (1.0 - rho) * prescribed


@dataclass
class RulePrescriptions:
    """Bundle of rule outputs alongside the inputs used to produce them."""
    inflation: float
    gap: float
    r_star: float
    taylor: float
    balanced: float
    inertial: float
    current_rate: float

    @property
    def gap_to_current(self) -> dict[str, float]:
        """How far each rule sits above (+) or below (-) the current rate."""
        return {
            "Taylor (1993)": self.taylor - self.current_rate,
            "Balanced approach": self.balanced - self.current_rate,
            "Inertial": self.inertial - self.current_rate,
        }


def compute(
    inflation: float,
    gap: float,
    current_rate: float,
    r_star: float = config.DEFAULT_R_STAR,
    target: float = config.INFLATION_TARGET,
    rho: float = config.DEFAULT_RHO,
) -> RulePrescriptions:
    """Compute all rule prescriptions for a single point in time."""
    t = taylor(inflation, gap, r_star=r_star, target=target)
    b = balanced_approach(inflation, gap, r_star=r_star, target=target)
    i = inertial(t, current_rate, rho=rho)
    return RulePrescriptions(
        inflation=inflation, gap=gap, r_star=r_star,
        taylor=t, balanced=b, inertial=i, current_rate=current_rate,
    )


def historical_prescriptions(
    inflation: pd.Series,
    unrate: pd.Series,
    u_star: pd.Series,
    fed_funds: pd.Series,
    r_star: float = config.DEFAULT_R_STAR,
    target: float = config.INFLATION_TARGET,
    start: str = "2015-01-01",
) -> pd.DataFrame:
    """Backcast the rules through history alongside the actual funds rate.

    All inputs are monthly series; ``u_star`` (quarterly CBO) is forward-filled
    onto the monthly grid. Returns columns: ff, taylor, balanced.
    """
    df = pd.DataFrame({
        "inflation": inflation,
        "u": unrate,
        "u_star": u_star.reindex(unrate.index, method="ffill"),
        "ff": fed_funds,
    }).dropna()
    gap = -config.OKUN_COEF * (df["u"] - df["u_star"])
    out = pd.DataFrame({
        "ff": df["ff"],
        "taylor": taylor(df["inflation"], gap, r_star=r_star, target=target),
        "balanced": balanced_approach(df["inflation"], gap, r_star=r_star, target=target),
    })
    return out[out.index >= pd.Timestamp(start)]


def forward_path(
    inflation_now: float,
    inflation_terminal: float,
    u_now: float,
    u_terminal: float,
    u_star: float,
    ff_now: float,
    quarters: int = 8,
    r_star: float = config.DEFAULT_R_STAR,
    target: float = config.INFLATION_TARGET,
    rho: float = config.DEFAULT_RHO,
) -> pd.DataFrame:
    """Project rule prescriptions forward under a linear-glide scenario.

    Inflation and unemployment glide linearly from today's value to a terminal
    assumption over ``quarters`` quarters; rules are evaluated along that path.
    The inertial rule is iterated quarter-by-quarter from the current rate.
    This is a *scenario*, not a forecast — assumptions are user-set.
    """
    infl = np.linspace(inflation_now, inflation_terminal, quarters)
    u = np.linspace(u_now, u_terminal, quarters)
    gap = -config.OKUN_COEF * (u - u_star)

    taylor_p = taylor(infl, gap, r_star=r_star, target=target)
    balanced_p = balanced_approach(infl, gap, r_star=r_star, target=target)

    inertial_p, prev = [], ff_now
    for t in taylor_p:
        prev = inertial(t, prev, rho=rho)
        inertial_p.append(prev)

    dates = pd.date_range(pd.Timestamp.today().normalize(), periods=quarters, freq="QS")
    return pd.DataFrame(
        {"taylor": taylor_p, "balanced": balanced_p, "inertial": inertial_p},
        index=dates,
    )
