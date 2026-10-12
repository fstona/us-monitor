"""Rates — policy stance, what markets price, the Treasury curve and the 10y."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config
from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import rates


def render() -> None:
    st.subheader("Rates — how restrictive is policy, and what do markets price?")
    start = ui.since()

    with ui.guard("Rates KPIs"):
        mid = ui.ff_mid()
        m, _ = ui.last(mid)
        two, d2 = ui.last(ui.load("DGS2"))
        ten, _ = ui.last(ui.load("DGS10"))
        core, _ = ui.last(ui.yoy("PCEPILFE"))
        r10, _ = ui.last(ui.load("DFII10"))
        tp, _ = ui.last(ui.load("THREEFYTP10"))
        c = st.columns(6)
        ui.metric(c[0], "Fed funds (target mid)", m)
        ui.metric(c[1], f"2y Treasury ({d2:%d %b})", two, delta=two - m,
                  delta_fmt="{:+.2f} vs FF", delta_color="off",
                  help="2y − funds mid < 0 ⇒ markets price cuts over ~2 years.")
        ui.metric(c[2], "10y Treasury", ten, delta=ten - two, delta_fmt="2s10s {:+.2f}",
                  delta_color="off")
        ui.metric(c[3], "Real FF (− core PCE)", m - core, "{:+.2f}%",
                  delta=m - core - config.DEFAULT_R_STAR,
                  delta_fmt=f"{{:+.2f}} vs r* {config.DEFAULT_R_STAR:.2f}", delta_color="off",
                  help="Above r* = restrictive. r* default from config (slider in Policy Rules).")
        ui.metric(c[4], "10y real (TIPS)", r10)
        ui.metric(c[5], "10y term premium", tp, help="Kim-Wright (Fed Board), zero-coupon 10y.")

    # --- Stance --------------------------------------------------------------------
    ui.section("1 · Policy stance — real policy rate vs neutral",
               "Ex-post real rate = funds rate minus inflation. Above r* is restrictive. Using the "
               "trimmed mean (Warsh's gauge) instead of core PCE changes the verdict when the two "
               "diverge.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Real policy rate"):
        ff_m = ui.ff_mid_monthly()
        ui.plot(charts.multiline("Real policy rate", {
            "FF − core PCE": rates.real_policy_rate(ff_m, ui.yoy("PCEPILFE")),
            f"FF − trimmed-mean PCE {WARSH}": rates.real_policy_rate(
                ff_m, ui.load("PCETRIM12M159SFRBDAL")),
            "FF − Cleveland 1y exp. (ex-ante)": rates.real_policy_rate(
                ff_m, ui.load("EXPINF1YR")),
        }, "%", start=start, hlines=[(config.DEFAULT_R_STAR, f"r* = {config.DEFAULT_R_STAR}%")]))
    with c2, ui.guard("Market-implied direction"):
        ui.plot(charts.multiline("What markets price: 2y Treasury − funds target mid", {
            "2y − FF mid": rates.market_implied_direction(ui.load("DGS2"), ui.ff_mid()),
        }, "pp", start=ui.since(5), hlines=[(0.0, "no change priced")]))
        st.caption("Proxy until the futures-based path lands (roadmap): clearly negative = "
                   "cuts priced over ~2 years; positive = hikes. Embeds a small term premium.")

    # --- Curve ---------------------------------------------------------------------
    ui.section("2 · The Treasury curve")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Yields"):
        ui.plot(charts.multiline("Treasury yields & funds rate", {
            "Fed funds mid": ui.ff_mid(), "3m": ui.load("DGS3MO"), "2y": ui.load("DGS2"),
            "10y": ui.load("DGS10"), "30y": ui.load("DGS30"),
        }, "%", start=start))
    with c2, ui.guard("Curve snapshot"):
        tenors = {t: ui.load(sid) for t, sid in rates.CURVE_TENORS.items()}
        snap = rates.curve_snapshot(tenors, {"3m ago": pd.DateOffset(months=3),
                                             "1y ago": pd.DateOffset(years=1)})
        ui.plot(charts.categorical_lines("Yield curve: today vs 3m and 1y ago", snap, "%"))
    with ui.guard("Curve slopes"):
        ui.plot(charts.multiline("Curve slopes (inversion = below zero)", {
            "10y − 2y": ui.load("T10Y2Y"), "10y − 3m": ui.load("T10Y3M"),
        }, "pp", start=start, hlines=[(0.0, "inversion")]))

    # --- 10y decomposition -----------------------------------------------------------
    ui.section("3 · Inside the 10-year",
               "Nominal 10y ≈ real yield (TIPS) + breakeven inflation. The term premium (Kim-Wright) "
               "is the extra compensation for duration risk — fiscal supply and inflation "
               "uncertainty push it up.")
    c1, c2 = st.columns(2)
    with c1, ui.guard("10y decomposition"):
        ui.plot(charts.multiline("10y nominal = real + breakeven", {
            "10y nominal": ui.load("DGS10"), "10y real (TIPS)": ui.load("DFII10"),
            "10y breakeven": ui.load("T10YIE"),
        }, "%", start=start))
    with c2, ui.guard("Term premium"):
        ui.plot(charts.multiline("10y term premium (Kim-Wright)", {
            "Term premium": ui.load("THREEFYTP10"),
        }, "%", start=start, hlines=ui.ZERO))
    st.caption(f"{WARSH} “The Fed needs clear market signals, as unfiltered as possible… the "
               "prices… of Treasury securities.”")
