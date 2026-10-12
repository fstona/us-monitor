"""Policy rules — where Taylor-type rules say the funds rate should be."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config
from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import policy_rules

# Inflation gauge choices for the rules: label -> loader.
INFLATION_MEASURES = {
    "Core PCE (y/y)": lambda: ui.yoy("PCEPILFE"),
    f"Trimmed-mean PCE 12m {WARSH}": lambda: ui.load("PCETRIM12M159SFRBDAL"),
    "Headline PCE (y/y)": lambda: ui.yoy("PCEPI"),
}


def sidebar_params() -> tuple[float, float, str]:
    st.sidebar.header("Policy-rule parameters")
    r_star = st.sidebar.slider("Neutral real rate r* (%)", 0.0, 2.5, config.DEFAULT_R_STAR, 0.25)
    rho = st.sidebar.slider("Inertia ρ", 0.0, 0.95, config.DEFAULT_RHO, 0.05)
    measure = st.sidebar.selectbox("Inflation gauge", list(INFLATION_MEASURES))
    return r_star, rho, measure


def unemployment_gap_inputs() -> tuple[float, float, float]:
    u, d = ui.last(ui.load("UNRATE"))
    u_star = ui.value_asof("NROU", d)
    return u, u_star, policy_rules.unemployment_to_output_gap(u, u_star)


def current_prescriptions(r_star: float, rho: float, measure: str) -> policy_rules.RulePrescriptions:
    pi, _ = ui.last(INFLATION_MEASURES[measure]())
    mid, _ = ui.last(ui.ff_mid())
    _, _, gap = unemployment_gap_inputs()
    return policy_rules.compute(pi, gap, mid, r_star=r_star, rho=rho)


def render(r_star: float, rho: float, measure: str) -> None:
    st.subheader("Policy-rule benchmark — where rules say the rate should be")
    try:
        infl = INFLATION_MEASURES[measure]()
        pi, _ = ui.last(infl)
        mid, _ = ui.last(ui.ff_mid())
        u, u_star, _ = unemployment_gap_inputs()
        rx = current_prescriptions(r_star, rho, measure)

        c = st.columns(4)
        ui.metric(c[0], "Funds rate (target mid)", mid)
        ui.metric(c[1], "Taylor (1993)", rx.taylor, delta=rx.taylor - mid,
                  delta_fmt="{:+.2f} vs now", delta_color="off")
        ui.metric(c[2], "Balanced approach", rx.balanced, delta=rx.balanced - mid,
                  delta_fmt="{:+.2f} vs now", delta_color="off")
        ui.metric(c[3], "Inertial", rx.inertial, delta=rx.inertial - mid,
                  delta_fmt="{:+.2f} vs now", delta_color="off")
        st.caption(f"Inputs: {measure} = {pi:.2f}%, unemployment {u:.1f}% vs CBO u* {u_star:.1f}% "
                   f"(Okun {config.OKUN_COEF}), r* = {r_star:.2f}%. Positive 'vs now' = the rule "
                   "wants a higher rate (policy looks loose vs the rule). Change the gauge and r* "
                   "in the sidebar.")

        # 1) Have the rules tracked the Fed? (no assumptions needed)
        hist = policy_rules.historical_prescriptions(
            infl, ui.load("UNRATE"), ui.load("NROU"), ui.load("FEDFUNDS"),
            r_star=r_star, start=ui.since())
        ui.plot(charts.multiline("Actual fed funds vs rule prescriptions (history)", {
            "Effective fed funds": hist["ff"], "Taylor (1993)": hist["taylor"],
            "Balanced approach": hist["balanced"],
        }, "%", start=ui.since()))

        # 2) Forward scenario (next 2 years)
        st.markdown("**Forward path — your 2-year scenario**")
        s1, s2 = st.columns(2)
        infl_term = s1.slider("Inflation in 2 years (%)", 1.0, 5.0, 2.0, 0.1)
        u_term = s2.slider("Unemployment in 2 years (%)", 3.0, 8.0, round(u_star, 1), 0.1)
        fwd = policy_rules.forward_path(
            inflation_now=pi, inflation_terminal=infl_term,
            u_now=u, u_terminal=u_term, u_star=u_star, ff_now=mid,
            quarters=8, r_star=r_star, rho=rho)

        three_y = pd.Timestamp.today() - pd.DateOffset(years=3)
        ff = ui.ff_mid()
        ff = ff[ff.index >= three_y]
        two = ui.load("DGS2")
        two = two[two.index >= three_y]
        today = pd.Timestamp.today().normalize()
        fig = charts.base_fig("Fed funds: actual vs rule-implied path (next 2 years)", "%")
        fig.add_trace(go.Scatter(x=ff.index, y=ff.values, mode="lines",
                                 name="Fed funds mid (actual)", line=dict(color="black", width=3)))
        fig.add_trace(go.Scatter(x=two.index, y=two.values, mode="lines",
                                 name="2y Treasury (market proxy)",
                                 line=dict(color="#888888", width=1.5)))
        for col, label in [("taylor", "Taylor"), ("balanced", "Balanced"), ("inertial", "Inertial")]:
            path = pd.concat([pd.Series({today: mid}), fwd[col]])
            fig.add_trace(go.Scatter(x=path.index, y=path.values, mode="lines",
                                     name=f"{label} (implied)", line=dict(dash="dash")))
        ui.plot(fig)
        st.caption("Forward lines apply each rule to a **linear glide** of inflation and "
                   "unemployment to your 2-year assumptions — a scenario, not a forecast. The "
                   "inertial path respects the Fed's gradualism (ρ smoothing). The 2y yield is "
                   "roughly the market's average expected funds rate over the next two years.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Policy rules could not be computed: {exc}")
