"""Inflation — level, momentum, underlying trend, breadth, composition, expectations."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config
from src.dashboard import charts, ui
from src.dashboard.ui import TARGET, WARSH
from src.transform import indicators, inflation


def render() -> None:
    st.subheader("Inflation — is it converging to 2%, clearly and at sufficient speed?")
    start = ui.since()

    with ui.guard("Inflation KPIs"):
        c = st.columns(5)
        core, d = ui.last(ui.yoy("PCEPILFE"))
        core6, _ = ui.last(ui.ann("PCEPILFE", 6))
        trim12, _ = ui.last(ui.load("PCETRIM12M159SFRBDAL"))
        trim6, _ = ui.last(ui.load("PCETRIM6M680SFRBDAL"))
        sc, _ = ui.last(ui.ann("IA001260M", 3))
        ui.metric(c[0], f"Core PCE y/y ({d:%b %y})", core, delta=core - 2, delta_color="inverse",
                  delta_fmt="{:+.2f} vs 2%")
        ui.metric(c[1], "Core PCE 6m ann.", core6, delta=core6 - core, delta_color="inverse",
                  delta_fmt="{:+.2f} vs y/y")
        ui.metric(c[2], f"Trimmed-mean PCE 12m {WARSH}", trim12, delta=trim12 - 2,
                  delta_color="inverse", delta_fmt="{:+.2f} vs 2%")
        ui.metric(c[3], f"Trimmed-mean PCE 6m {WARSH}", trim6, delta=trim6 - trim12,
                  delta_color="inverse", delta_fmt="{:+.2f} vs 12m")
        ui.metric(c[4], "Supercore PCE 3m ann.", sc, delta=sc - 2, delta_color="inverse",
                  delta_fmt="{:+.2f} vs 2%")
        st.caption("Deltas in red = further from target / re-accelerating. "
                   "6m below 12m means the trend is still converging.")

    # --- Level --------------------------------------------------------------
    ui.section("1 · Realized inflation")
    with ui.guard("Realized inflation"):
        ui.plot(charts.multiline("Realized inflation (y/y %)", {
            "Core PCE": ui.yoy("PCEPILFE"), "Headline PCE": ui.yoy("PCEPI"),
            "Core CPI": ui.yoy("CPILFESL"), "Headline CPI": ui.yoy("CPIAUCSL"),
        }, "%", start=start, hlines=TARGET))

    # --- Momentum -------------------------------------------------------------
    ui.section("2 · Momentum — the short window turns first",
               f"{WARSH} Warsh reads 12m and 6m together: “the 12-month change… 3.7 percent… "
               "six-month change is 4.1 percent” — a shorter window above the longer one means "
               "disinflation has lost traction.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Headline PCE momentum"):
        ui.plot(charts.multiline(f"Headline PCE — 12m vs 6m ann. {WARSH}", {
            "PCE 12m": ui.yoy("PCEPI"), "PCE 6m ann.": ui.ann("PCEPI", 6),
        }, "%", start=start, hlines=TARGET))
    with c2, ui.guard("Core PCE momentum"):
        ui.plot(charts.multiline("Core PCE momentum cascade", {
            "Core PCE y/y": ui.yoy("PCEPILFE"), "6m ann.": ui.ann("PCEPILFE", 6),
            "3m ann.": ui.ann("PCEPILFE", 3),
        }, "%", start=ui.since(5), hlines=TARGET))

    # --- Underlying -------------------------------------------------------------
    ui.section(f"3 · Underlying trend — trimmed-mean & median gauges {WARSH}",
               "Trimmed-mean/median measures drop the most extreme price moves each month to "
               "expose the central trend — Chair Warsh's preferred lens (Dallas trimmed-mean PCE). "
               "Caveat: they understated the 2021–22 surge by trimming the early outliers.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Trimmed-mean PCE"):
        ui.plot(charts.multiline(f"Dallas trimmed-mean PCE vs headline {WARSH}", {
            "Headline PCE 12m": ui.yoy("PCEPI"),
            "Trimmed mean 12m": ui.load("PCETRIM12M159SFRBDAL"),
            "Trimmed mean 6m ann.": ui.load("PCETRIM6M680SFRBDAL"),
        }, "%", start=start, hlines=TARGET))
    with c2, ui.guard("Underlying gauges"):
        ui.plot(charts.multiline("Other underlying gauges (12m)", {
            "Core PCE": ui.yoy("PCEPILFE"), "Core CPI": ui.yoy("CPILFESL"),
            "Cleveland median CPI": ui.load("MEDCPIM159SFRBCLE"),
            "Cleveland 16% trimmed CPI": ui.load("TRMMEANCPIM159SFRBCLE"),
            "Atlanta sticky core CPI": ui.load("CORESTICKM159SFRBATL"),
        }, "%", start=start, hlines=TARGET))

    # --- Breadth ----------------------------------------------------------------
    ui.section(f"4 · Breadth — how many prices are rising fast? {WARSH}",
               "“I find it instructive to disaggregate the 199 individual components of the PCE.” "
               "Share of PCE components (by count) with price growth above 3%, computed from BEA "
               "Table 2.4.4U.")
    with ui.guard("PCE diffusion (BEA)"):
        fig = charts.multiline("PCE components with inflation > 3% (% of components)", {
            "12m": ui.load("BEA_PCE_DIFF12"), "6m ann.": ui.load("BEA_PCE_DIFF6"),
        }, "% of components", start="2005-01-01", hlines=[
            (config.DIFFUSION_PRE_PANDEMIC, f"~{config.DIFFUSION_PRE_PANDEMIC:.0f}% pre-pandemic avg"),
            (config.DIFFUSION_PEAK, f"~{config.DIFFUSION_PEAK:.0f}% post-pandemic peak"),
        ])
        ui.plot(fig)

    # --- Composition --------------------------------------------------------------
    ui.section("5 · Composition — Powell's three buckets",
               "Core CPI split into core goods, shelter and supercore (core services ex-shelter). "
               "Contributions = component y/y × share of core; supercore is the residual so bars "
               "sum to core. Weights in config.CPI_CORE_WEIGHTS — refresh from BLS yearly.")
    with ui.guard("Core CPI contributions"):
        contrib = inflation.core_cpi_contributions(
            ui.load("CPILFESL"), ui.load("CUSR0000SACL1E"), ui.load("CUSR0000SAH1"))
        contrib = contrib.resample("QE").last().tail(12)
        labels = [f"{d.year}Q{d.quarter}" for d in contrib.index]
        contrib.index = labels
        total = pd.Series(contrib.sum(axis=1).values, index=labels)
        ui.plot(charts.stacked_bar("Core CPI contributions (y/y, by quarter)", contrib, total,
                                   "pp of core inflation", total_label="Core CPI"))
    c1, c2 = st.columns(2)
    with c1, ui.guard("Supercore"):
        ui.plot(charts.multiline("Supercore — PCE services ex energy & housing", {
            "y/y": ui.yoy("IA001260M"), "6m ann.": ui.ann("IA001260M", 6),
            "3m ann.": ui.ann("IA001260M", 3),
        }, "%", start=ui.since(5), hlines=TARGET))
    with c2, ui.guard("Energy wedge"):
        ui.plot(charts.multiline("Energy & the headline-vs-core wedge", {
            "Headline CPI": ui.yoy("CPIAUCSL"), "Core CPI": ui.yoy("CPILFESL"),
            "CPI energy": ui.yoy("CPIENGSL"),
        }, "%", start=start, hlines=TARGET, clip=0.02))

    c1, c2 = st.columns(2)
    with c1, ui.guard("Commodities"):
        ui.plot(charts.multiline(f"Commodity prices — PPI all commodities {WARSH}", {
            "PPI commodities y/y": ui.yoy("PPIACO"), "PPI final demand y/y": ui.yoy("PPIFIS"),
        }, "%", start=start, hlines=ui.ZERO))
    with c2, ui.guard("Oil"):
        ui.plot(charts.multiline("WTI crude oil (US$/bbl, monthly avg)", {
            "WTI": ui.monthly("DCOILWTICO", "mean"),
        }, "US$/bbl", start=start))
    st.caption(f"{WARSH} “The recent rise in overall commodity prices also bears watching.” "
               "Core excludes energy by construction — oil reaches core only through second-round "
               "effects.")

    # --- Expectations -------------------------------------------------------------
    ui.section(f"6 · Expectations — survey, model and market {WARSH}",
               "“It's the Fed's job to make sure that inflation expectations do not get "
               "unanchored.” Two families, side by side (different nature, not a dual axis).")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Survey/model expectations"):
        ui.plot(charts.multiline("Surveys & model", {
            "UMich 1y (survey)": ui.load("MICH"),
            "Cleveland Fed 1y (model)": ui.load("EXPINF1YR"),
            "Cleveland Fed 5y (model)": ui.load("EXPINF5YR"),
        }, "%", start=start, hlines=TARGET))
    with c2, ui.guard("Market expectations"):
        ui.plot(charts.multiline("Market-implied (breakevens)", {
            "5y5y forward": ui.monthly("T5YIFR"), "10y breakeven": ui.monthly("T10YIE"),
        }, "%", start=start, hlines=TARGET))
