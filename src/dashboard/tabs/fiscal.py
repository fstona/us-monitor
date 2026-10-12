"""Fiscal — deficit, debt, interest burden and debt dynamics (r vs g)."""
from __future__ import annotations

import streamlit as st

from src.dashboard import charts, ui
from src.transform import fiscal


def render() -> None:
    st.subheader("Fiscal — how big is the deficit, and is debt on a stable path?")
    start = ui.since(20)

    with ui.guard("Fiscal frame"):
        gdp = ui.load("GDP")
        bal = fiscal.balance_12m_pct_gdp(ui.load("MTSDS133FMS"), gdp)
        debt_pub = fiscal.ratio_pct(ui.load("FYGFDPUN") / 1e3, gdp)
        interest = ui.load("A091RC1Q027SBEA")
        int_gdp = fiscal.ratio_pct(interest, gdp)
        int_rev = (interest / ui.load("FGRECPT") * 100).dropna()
        r_eff = fiscal.effective_interest_rate(interest, ui.load("FYGFDPUN"))
        g_nom = ui.yoy("GDP")

        c = st.columns(5)
        b, d = ui.last(bal)
        ui.metric(c[0], f"Budget balance 12m ({d:%b %y})", b, "{:+.1f}% GDP",
                  help="Rolling 12-month Monthly Treasury Statement balance ÷ nominal GDP.")
        dp, dq = ui.last(debt_pub)
        ui.metric(c[1], f"Debt held by public ({dq.year}Q{dq.quarter})", dp, "{:.0f}% GDP")
        ig, _ = ui.last(int_gdp)
        ui.metric(c[2], "Interest payments", ig, "{:.1f}% GDP")
        ir, _ = ui.last(int_rev)
        ui.metric(c[3], "Interest / receipts", ir, "{:.1f}%")
        r, _ = ui.last(r_eff)
        g, _ = ui.last(g_nom)
        ui.metric(c[4], "r − g", r - g, "{:+.1f} pp",
                  help=f"Effective rate on debt {r:.1f}% − nominal GDP growth {g:.1f}%. "
                       "> 0 ⇒ debt/GDP rises even with a balanced primary budget.")

    ui.section("1 · Deficit")
    with ui.guard("Deficit"):
        ui.plot(charts.multiline("Federal budget balance — rolling 12m (% of GDP)", {
            "Balance (− = deficit)": bal,
        }, "% of GDP", start=start, hlines=ui.ZERO))

    ui.section("2 · Debt & interest burden")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Debt"):
        ui.plot(charts.multiline("Federal debt (% of GDP)", {
            "Held by the public": debt_pub, "Total public debt": ui.load("GFDEGDQ188S"),
        }, "% of GDP", start=start))
    with c2, ui.guard("Interest"):
        ui.plot(charts.multiline("Interest burden", {
            "Interest / GDP (%)": int_gdp, "Interest / federal receipts (%)": int_rev,
        }, "%", start=start))

    ui.section("3 · Debt dynamics — r vs g",
               "When the average rate on the debt (r) rises above nominal growth (g), debt/GDP "
               "grows on its own. The effective rate reprices slowly toward market yields as debt "
               "rolls over — compare with the 10y.")
    with ui.guard("r vs g"):
        ui.plot(charts.multiline("Effective interest rate vs nominal GDP growth vs 10y", {
            "Effective rate on debt (r)": r_eff, "Nominal GDP growth y/y (g)": g_nom,
            "10y Treasury": ui.monthly("DGS10"),
        }, "%", start=start, clip=0.02))
