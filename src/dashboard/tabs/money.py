"""Money & liquidity — M2 vs nominal GDP, velocity, the Fed's balance sheet."""
from __future__ import annotations

import streamlit as st

from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import money


def render() -> None:
    st.subheader("Money & liquidity")
    start = ui.since()

    with ui.guard("Liquidity frame"):
        liq = money.fed_liquidity(ui.load("WALCL"), ui.load("WTREGEN"),
                                  ui.load("RRPONTSYD"), ui.load("WRESBAL"))
        lastrow = liq.iloc[-1]
        yr = liq.iloc[-53] if len(liq) > 53 else liq.iloc[0]
        c = st.columns(5)
        m2, d = ui.last(ui.yoy("M2SL"))
        ui.metric(c[0], f"M2 y/y ({d:%b %y}) {WARSH}", m2, "{:.1f}%")
        for col, key in zip(c[1:], ["Fed total assets", "Reserves", "TGA", "Net liquidity"]):
            ui.metric(col, f"{key} ({liq.index[-1]:%d %b})", lastrow[key], "${:.2f}tn",
                      delta=lastrow[key] - yr[key], delta_fmt="{:+.2f}tn 1y", delta_color="off")

    ui.section(f"1 · Money matters {WARSH}",
               "“Money matters. It's not fashionable these days.” Money × velocity ≈ nominal "
               "spending: M2 growth persistently above nominal GDP growth at 2% inflation (≈4%) "
               "is a warning — the 2020–21 surge preceded the inflation.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("M2 vs GDP"):
        ui.plot(charts.multiline("M2 vs nominal GDP (y/y %)", {
            "M2": ui.yoy("M2SL"), "Nominal GDP": ui.yoy("GDP"),
        }, "%", start=ui.since(20), clip=0.02, hlines=[(4.0, "≈ 2% inflation + trend growth")]))
    with c2, ui.guard("Velocity"):
        ui.plot(charts.multiline("Velocity of M2 (nominal GDP ÷ M2)", {
            "M2 velocity": ui.load("M2V"),
        }, "ratio", start=ui.since(20)))

    ui.section("2 · The Fed's balance sheet",
               "Net liquidity = Fed assets − Treasury General Account − ON RRP: the reserves the "
               "balance sheet leaves in private hands. A smaller balance sheet is a stated Warsh "
               "priority — watch reserves for signs of scarcity (repo stress).")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Balance sheet"):
        ui.plot(charts.multiline("Fed assets, reserves & net liquidity (US$ tn)", {
            k: liq[k] for k in ["Fed total assets", "Reserves", "Net liquidity"]
        }, "US$ tn", start=start))
    with c2, ui.guard("Drains"):
        ui.plot(charts.multiline("Liquidity drains: TGA & ON RRP (US$ tn)", {
            k: liq[k] for k in ["TGA", "ON RRP"]
        }, "US$ tn", start=start))
