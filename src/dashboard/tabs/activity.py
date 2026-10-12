"""Activity — GDP & nowcast, private demand (PDFP), capex, consumption, industry,
housing, profits."""
from __future__ import annotations

import streamlit as st

from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import policy_rules


def render() -> None:
    st.subheader("Activity — how strong is private demand?")
    start = ui.since()

    with ui.guard("Activity KPIs"):
        c = st.columns(6)
        g, d = ui.last(ui.load("A191RL1Q225SBEA"))
        ui.metric(c[0], f"Real GDP q/q ann. ({d.year}Q{d.quarter})", g, "{:.1f}%")
        now, dn = ui.last(ui.load("GDPNOW"))
        ui.metric(c[1], f"GDPNow ({dn.year}Q{dn.quarter})", now, "{:.1f}%",
                  help="Atlanta Fed nowcast for the current/most recent quarter.")
        p, _ = ui.last(ui.yoy("LB0000031Q020SBEA"))
        ui.metric(c[2], f"PDFP 4Q {WARSH}", p, "{:.1f}%")
        gdp = ui.load("GDPC1")
        gap = policy_rules.output_gap(float(gdp.iloc[-1]), ui.value_asof("GDPPOT", gdp.index[-1]))
        ui.metric(c[3], "Output gap (CBO)", gap, "{:+.1f}%")
        rp, _ = ui.last(ui.yoy("PCEC96"))
        ui.metric(c[4], "Real consumption y/y", rp, "{:.1f}%")
        ip, _ = ui.last(ui.yoy("INDPRO"))
        ui.metric(c[5], "Industrial prod. y/y", ip, "{:.1f}%")

    # --- GDP ------------------------------------------------------------------------
    ui.section(f"1 · GDP vs private domestic demand {WARSH}",
               "“PDFP… typically carries more signal than gross domestic product.” PDFP strips "
               "inventories, trade and government from GDP, leaving private domestic demand.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("GDP & nowcast"):
        ui.plot(charts.multiline("Real GDP (q/q ann.) & GDPNow", {
            "Real GDP": ui.load("A191RL1Q225SBEA"), "GDPNow (final nowcast)": ui.load("GDPNOW"),
        }, "%", start=start, clip=0.03, dashed=("GDPNow (final nowcast)",), hlines=ui.ZERO))
    with c2, ui.guard("PDFP"):
        ui.plot(charts.multiline(f"PDFP vs GDP (4-quarter growth) {WARSH}", {
            "PDFP": ui.yoy("LB0000031Q020SBEA"), "Real GDP": ui.yoy("GDPC1"),
        }, "%", start=start, clip=0.03, hlines=ui.ZERO))

    # --- Investment -------------------------------------------------------------------
    ui.section(f"2 · Business investment — “the seed corn of future growth” {WARSH}",
               "“More than half of the cap-ex growth this year can likely be ascribed to the "
               "buildout related to AI.” Equipment and intellectual property (software, R&D).")
    with ui.guard("Capex"):
        ui.plot(charts.multiline("Real business investment (4-quarter growth)", {
            "Equipment": ui.yoy("Y033RX1Q020SBEA"),
            "Intellectual property": ui.yoy("Y001RX1Q020SBEA"),
        }, "%", start=start, clip=0.02, hlines=ui.ZERO))

    # --- Consumer -----------------------------------------------------------------------
    ui.section("3 · Consumer")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Consumption"):
        ui.plot(charts.multiline(f"Consumer spending (y/y %) {WARSH}", {
            "Real PCE": ui.yoy("PCEC96"), "Retail sales (nominal)": ui.yoy("RSAFS"),
        }, "%", start=start, clip=0.03, hlines=ui.ZERO))
    with c2, ui.guard("Sentiment"):
        ui.plot(charts.multiline("UMich consumer sentiment", {
            "Sentiment": ui.load("UMCSENT"),
        }, "index", start=start))

    # --- Industry & housing ----------------------------------------------------------------
    ui.section("4 · Industry & housing")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Industry"):
        ui.plot(charts.multiline("Industrial production (y/y %)", {
            "IP": ui.yoy("INDPRO"),
        }, "%", start=start, clip=0.02, hlines=ui.ZERO))
    with c2, ui.guard("Capacity utilization"):
        ui.plot(charts.multiline("Capacity utilization (%)", {
            "TCU": ui.load("TCU"),
        }, "%", start=start, clip=0.02))
    c1, c2 = st.columns(2)
    with c1, ui.guard("Housing"):
        ui.plot(charts.multiline(f"Housing starts & permits (k, SAAR) {WARSH}", {
            "Starts": ui.load("HOUST"), "Permits": ui.load("PERMIT"),
        }, "thousands", start=start))
    with c2, ui.guard("Mortgage rate"):
        ui.plot(charts.multiline("30y mortgage rate vs 10y Treasury", {
            "30y mortgage": ui.monthly("MORTGAGE30US"), "10y Treasury": ui.monthly("DGS10"),
        }, "%", start=start))
    st.caption(f"{WARSH} “Certain sectors — like housing and agriculture — are showing strains.”")

    # --- Profits ---------------------------------------------------------------------------
    ui.section(f"5 · Corporate profits {WARSH}",
               "“Profits have grown by more than 20 percent… profit margins are quite elevated.” "
               "Warsh watches the second derivative — the change in the growth rate.")
    with ui.guard("Profits"):
        ui.plot(charts.multiline("Corporate profits after tax (4-quarter growth)", {
            "Profits": ui.yoy("CPATAX"),
        }, "%", start=start, clip=0.03, hlines=ui.ZERO))
