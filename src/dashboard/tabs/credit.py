"""Credit & risk — spreads, volatility, equities, financial conditions, bank lending."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import indicators


def render() -> None:
    st.subheader("Credit & risk — are financial conditions restrictive?")
    start = ui.since()

    with ui.guard("Credit KPIs"):
        c = st.columns(5)
        hy, d = ui.last(ui.load("BAMLH0A0HYM2"))
        ui.metric(c[0], f"HY OAS ({d:%d %b})", hy, "{:.2f} pp")
        ig, _ = ui.last(ui.load("BAMLC0A0CM"))
        ui.metric(c[1], "IG OAS", ig, "{:.2f} pp")
        vix, _ = ui.last(ui.load("VIXCLS"))
        ui.metric(c[2], "VIX", vix, "{:.1f}")
        nf, _ = ui.last(ui.load("NFCI"))
        ui.metric(c[3], "NFCI", nf, "{:+.2f}", help="0 = average conditions; < 0 = looser.")
        spx = ui.load("SP500")
        chg = indicators.change_over(spx, pd.DateOffset(years=1))
        ui.metric(c[4], "S&P 500", float(spx.iloc[-1]), "{:,.0f}", delta=chg,
                  delta_fmt="{:+.1f}% 1y")
    st.caption(f"{WARSH} “I would be hard pressed to describe broad financial conditions as "
               "restrictive.”")

    ui.section(f"1 · Credit spreads {WARSH}",
               "Option-adjusted spreads over Treasuries. Separate panels: HY trades at 3–4 pp, IG "
               "near 1 pp. Note: FRED now carries only ~3 years of ICE BofA history (licensing).")
    c1, c2 = st.columns(2)
    with c1, ui.guard("HY OAS"):
        ui.plot(charts.multiline("High-yield OAS", {"HY OAS": ui.load("BAMLH0A0HYM2")},
                                 "pp", recession=False))
    with c2, ui.guard("IG OAS"):
        ui.plot(charts.multiline("Investment-grade OAS", {"IG OAS": ui.load("BAMLC0A0CM")},
                                 "pp", recession=False))

    ui.section("2 · Risk appetite")
    c1, c2 = st.columns(2)
    with c1, ui.guard("VIX"):
        ui.plot(charts.multiline("VIX (monthly avg)", {"VIX": ui.monthly("VIXCLS", "mean")},
                                 "index", start=start))
    with c2, ui.guard("S&P 500"):
        ui.plot(charts.multiline("S&P 500", {"S&P 500": ui.load("SP500")}, "index",
                                 start=start, recession=False))

    ui.section(f"3 · Financial conditions & bank credit {WARSH}",
               "“Standards… are on the easier end of their historical range. Credit and loan "
               "markets are showing few signs of policy restraint.”")
    c1, c2 = st.columns(2)
    with c1, ui.guard("NFCI"):
        ui.plot(charts.multiline("Chicago Fed NFCI (> 0 = tighter than average)", {
            "NFCI": ui.load("NFCI"),
        }, "index", start=ui.since(20), hlines=[(0.0, "average")], clip=0.01))
    with c2, ui.guard("SLOOS"):
        ui.plot(charts.multiline("SLOOS — net % of banks tightening C&I standards", {
            "Net % tightening": ui.load("DRTSCILM"),
        }, "net %", start=ui.since(20), hlines=[(0.0, "")]))
    with ui.guard("C&I loans"):
        ui.plot(charts.multiline("C&I loans (y/y %)", {"C&I loans": ui.yoy("TOTCI")}, "%",
                                 start=ui.since(20), hlines=ui.ZERO))
