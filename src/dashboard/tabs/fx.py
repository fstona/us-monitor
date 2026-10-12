"""Dollar & FX — broad dollar, AFE vs EM, majors and BRL.

Convention: every change is shown as DOLLAR STRENGTH (+ = USD appreciated).
EUR/USD is quoted USD per EUR, so it is inverted; the rest are foreign per USD.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard import charts, ui
from src.dashboard.ui import WARSH
from src.transform import indicators

# id -> (display name, invert to get "foreign currency per USD")
PAIRS: dict[str, tuple[str, bool]] = {
    "DTWEXBGS": ("Broad dollar index", False),
    "DTWEXAFEGS": ("Dollar vs advanced economies", False),
    "DTWEXEMEGS": ("Dollar vs emerging markets", False),
    "DEXUSEU": ("EUR (USD vs euro)", True),
    "DEXJPUS": ("JPY", False),
    "DEXCHUS": ("CNY", False),
    "DEXMXUS": ("MXN", False),
    "DEXBZUS": ("BRL", False),
}


def usd_strength(series_id: str) -> pd.Series:
    """Level oriented so that up = stronger dollar."""
    s = ui.load(series_id).dropna()
    return 1 / s if PAIRS[series_id][1] else s


def performance_table() -> pd.DataFrame:
    rows = []
    for sid, (name, _) in PAIRS.items():
        s = usd_strength(sid)
        ytd_base = s[s.index < pd.Timestamp(s.index[-1].year, 1, 1)]
        ytd = (s.iloc[-1] / ytd_base.iloc[-1] - 1) * 100 if len(ytd_base) else None
        raw = ui.load(sid).dropna()
        rows.append({
            "Dollar vs": name,
            "Last quote": f"{raw.iloc[-1]:,.4g}",
            "As of": f"{raw.index[-1]:%d %b %Y}",
            "1m %": indicators.change_over(s, pd.DateOffset(months=1)),
            "3m %": indicators.change_over(s, pd.DateOffset(months=3)),
            "YTD %": ytd,
            "1y %": indicators.change_over(s, pd.DateOffset(years=1)),
        })
    return pd.DataFrame(rows)


def render() -> None:
    st.subheader("Dollar & FX — where is the dollar going, and against whom?")
    start = ui.since()

    ui.section("1 · Scoreboard (+ = dollar stronger)",
               "H.10 exchange rates are published weekly with ~1 week lag.")
    with ui.guard("FX table"):
        tbl = performance_table()
        num = ["1m %", "3m %", "YTD %", "1y %"]
        st.dataframe(
            tbl.style.format({c: "{:+.1f}" for c in num}, na_rep="—")
               .background_gradient(subset=num, cmap="RdBu_r", vmin=-10, vmax=10),
            hide_index=True, width="stretch")

    ui.section("2 · Trade-weighted dollar")
    c1, c2 = st.columns(2)
    with c1, ui.guard("Broad dollar"):
        ui.plot(charts.multiline(f"Broad dollar index (nominal) {WARSH}", {
            "Broad": ui.load("DTWEXBGS"),
        }, "index", start=start))
    with c2, ui.guard("AFE vs EM"):
        ui.plot(charts.multiline("Dollar vs advanced vs emerging (rebased = 100)", {
            "vs advanced economies": indicators.rebase(ui.load("DTWEXAFEGS"), start),
            "vs emerging markets": indicators.rebase(ui.load("DTWEXEMEGS"), start),
        }, "index", start=start))
    st.caption(f"{WARSH} “The foreign exchange value of the dollar” is one of the unfiltered "
               "market signals the Chair says he wants to read directly.")

    ui.section("3 · Bilateral (dollar strength, rebased = 100)")
    with ui.guard("Majors"):
        ui.plot(charts.multiline("USD vs EUR, JPY, CNY, MXN, BRL (up = stronger dollar)", {
            PAIRS[sid][0]: indicators.rebase(usd_strength(sid), start)
            for sid in ["DEXUSEU", "DEXJPUS", "DEXCHUS", "DEXMXUS", "DEXBZUS"]
        }, "index", start=start))
    c1, c2 = st.columns(2)
    with c1, ui.guard("Real yields vs dollar"):
        ui.plot(charts.multiline("10y real yield (TIPS) — a driver of the dollar", {
            "10y real": ui.monthly("DFII10"),
        }, "%", start=start))
    with c2, ui.guard("USD/BRL"):
        ui.plot(charts.multiline("USD/BRL", {"BRL per USD": ui.load("DEXBZUS")},
                                 "BRL", start=start))
