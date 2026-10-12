"""Labor — headline flow, tightness (Michaillat–Saez), supply, wages & ULC."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config
from src.dashboard import charts, ui
from src.dashboard.ui import WARSH


def render() -> None:
    st.subheader("Labor market — tightness, not just the unemployment rate")
    start = ui.since()

    with ui.guard("Labor KPIs"):
        df = ui.labor_frame()
        lf = df.iloc[-1]
        pay = ui.load("PAYEMS").diff()
        c = st.columns(5)
        ui.metric(c[0], f"Payrolls ({pay.index[-1]:%b %y})", pay.iloc[-1], "{:+,.0f}k",
                  delta=pay.tail(3).mean(), delta_fmt="3m avg {:+,.0f}k", delta_color="off")
        u, d = ui.last(ui.load("UNRATE"))
        u_star = ui.value_asof("NROU", d)
        ui.metric(c[1], "Unemployment", u, "{:.1f}%", delta=u - u_star,
                  delta_fmt="{:+.1f} vs CBO u*", delta_color="off")
        ui.metric(c[2], "Tightness θ (v/u)", lf["tightness"], "{:.2f}",
                  delta=lf["tightness"] - 1, delta_fmt="{:+.2f} vs 1", delta_color="off")
        cl, _ = ui.last(ui.load("IC4WSA"))
        ui.metric(c[3], f"Initial claims 4wk {WARSH}", cl / 1e3, "{:,.0f}k")
        q, _ = ui.last(ui.load("JTSQUR"))
        ui.metric(c[4], "Quits rate", q, "{:.1f}%")

    # --- Headline flow ------------------------------------------------------------
    ui.section("1 · Job creation & layoffs (real-time signals)")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Payrolls"):
        ui.plot(charts.bars("Nonfarm payrolls — monthly change (k)", ui.load("PAYEMS").diff(),
                            "thousands", start=start, avg_window=3, avg_label="3m avg", clip=0.03))
    with c2, ui.guard("Claims"):
        ui.plot(charts.multiline(f"Jobless claims {WARSH}", {
            "Initial claims (4-wk avg)": ui.load("IC4WSA") / 1e3,
            "Continuing claims": ui.load("CCSA") / 1e3,
        }, "thousands", start=start, clip=0.02))
    st.caption(f"{WARSH} Claims are “an empirically robust real-time indicator… near their lowest "
               "level in decades.” Payrolls: “when labor supply is barely growing, monthly job "
               "gains are naturally going to run low.” Axes clipped by quantile so 2020 does not "
               "flatten the recent range.")

    # --- Tightness -----------------------------------------------------------------
    ui.section("2 · Tightness — Michaillat–Saez framework",
               "θ = v/u (vacancies per unemployed; 1 = full employment) · FERU u* = √(u·v) · "
               "gap = u − u*. θ > 1, a negative gap and high quits all signal a tight market.")
    with ui.guard("Tightness"):
        df = ui.labor_frame()
        c1, c2 = st.columns(2)
        with c1:
            ui.plot(charts.multiline("Unemployment rate vs vacancy rate (inputs to θ)",
                    {"Unemployment u": df["u"], "Vacancy rate v": df["v"]},
                    "% of labor force", start="2001-01-01", clip=0.01))
        with c2:
            ui.plot(charts.multiline("Labor market tightness θ = v/u",
                    {"θ (vacancies per unemployed)": df["tightness"]}, "ratio",
                    start="2001-01-01", hlines=[(1.0, "θ = 1 (full employment)")]))
        c1, c2 = st.columns(2)
        with c1:
            ui.plot(charts.multiline("Unemployment vs FERU (u* = √(u·v))",
                    {"Unemployment u": df["u"], "FERU u*": df["feru"]}, "%",
                    start="2001-01-01", clip=0.01))
        with c2:
            ui.plot(beveridge_curve(df))

    # --- Supply ----------------------------------------------------------------------
    ui.section(f"3 · Labor supply & churn {WARSH}",
               "“Labor supply is barely growing… people who want to work, by and large, are "
               "holding or finding jobs.”")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Participation"):
        ui.plot(charts.multiline("Participation & prime-age employment", {
            "Participation rate": ui.load("CIVPART"),
            "Prime-age (25–54) EPOP": ui.load("LNS12300060"),
        }, "%", start=start, clip=0.02))
    with c2, ui.guard("Quits"):
        ui.plot(charts.multiline("Quits & job-openings rates — voluntary churn", {
            "Quits rate": ui.load("JTSQUR"), "Job-openings rate": ui.load("JTSJOR"),
        }, "%", start=start))
    with ui.guard("U-3 vs U-6"):
        ui.plot(charts.multiline("Unemployment U-3 vs underemployment U-6", {
            "U-3": ui.load("UNRATE"), "U-6": ui.load("U6RATE"),
        }, "%", start=start, clip=0.02))

    # --- Wages & ULC ---------------------------------------------------------------
    ui.section("4 · Wages & unit labor costs — the supercore driver",
               "Clarida's lens (New-Keynesian Phillips curve): inflation tracks unit labor costs "
               "(wages net of productivity), not raw wages. Warsh goes further: “wage growth has "
               "not proven a reliable indicator of future inflation” — context, not a guide.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Wages"):
        ui.plot(charts.multiline("Wage growth (y/y %)", {
            "ECI total comp": ui.yoy("ECIALLCIV"), "ECI wages & salaries": ui.yoy("ECIWAG"),
            "Atlanta Wage Tracker": ui.load("FRBATLWGT3MMAUMHWGO"),
            "Avg hourly earnings": ui.yoy("CES0500000003"),
        }, "%", start=start, clip=0.02))
    with c2, ui.guard("ULC"):
        ui.plot(charts.multiline("Unit labor costs vs supercore (ULC = comp − productivity)", {
            "Compensation/hour": ui.yoy("COMPNFB"), "Productivity": ui.yoy("OPHNFB"),
            "Unit labor costs": ui.yoy("ULCNFB"), "Supercore PCE": ui.yoy("IA001260M"),
        }, "%", start=start, hlines=[(config.INFLATION_TARGET, "2% target")], clip=0.02))


def beveridge_curve(df: pd.DataFrame) -> go.Figure:
    fig = charts.base_fig("Beveridge curve", "Vacancy rate v (%)")
    fig.update_layout(hovermode="closest")
    color = df.index.year + (df.index.month - 1) / 12
    fig.add_trace(go.Scatter(
        x=df["u"], y=df["v"], mode="markers+lines",
        marker=dict(size=5, color=color, colorscale="Viridis",
                    showscale=True, colorbar=dict(title="Year")),
        line=dict(width=0.5, color="lightgray"), name="path", showlegend=False))
    last = df.iloc[-1]
    fig.add_trace(go.Scatter(x=[last["u"]], y=[last["v"]], mode="markers+text",
                  marker=dict(size=12, color="#c00000"),
                  text=[f"{df.index[-1]:%b %Y}"], textposition="top center", name="latest"))
    lim = [0, max(df["u"].max(), df["v"].max()) * 1.1]
    fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines",
                  line=dict(dash="dot", color="gray"), name="v = u (θ = 1)"))
    fig.update_xaxes(title="Unemployment rate u (%)")
    return fig
