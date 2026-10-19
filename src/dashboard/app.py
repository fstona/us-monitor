"""US Monitor — Streamlit dashboard.

Run from the project root:
    streamlit run src/dashboard/app.py

Each tab lives in ``src/dashboard/tabs/<name>.py`` with a ``render()``; shared
helpers (cached loader, lookback, error guards) are in ``ui.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project importable when launched via `streamlit run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import base64

import streamlit as st

from src import data, store
from src.dashboard import ui
from src.dashboard.tabs import (activity, credit, fedspeak, fiscal, fx, inflation, labor,
                                money, overview, policy, rates)

# Flag as an image, not the 🇺🇸 emoji: Windows doesn't draw flag emojis (shows "US").
FLAG = Path(__file__).resolve().parents[2] / "assets" / "us_flag.png"
st.set_page_config(page_title="US Monitor", page_icon=str(FLAG), layout="wide")


def sidebar() -> tuple[float, float, str]:
    st.sidebar.header("View")
    st.sidebar.select_slider("History (years)", options=[3, 5, 10, 15, 20, 30], value=10,
                             key="lookback_years")
    st.sidebar.caption("★ = analysis drawn from Chair Warsh's Jackson Hole 2026 keynote.")
    if data.can_refresh():
        if st.sidebar.button("↻ Refresh all data", help="Every series + Fed speakers (≈6 min). "
                             "Each tab also has its own refresh button."):
            ui.refresh_all()
        msg = st.session_state.pop("_refresh_all_msg", None)
        if msg:
            st.sidebar.success(msg)
    return policy.sidebar_params()


def main() -> None:
    flag = base64.b64encode(FLAG.read_bytes()).decode()
    st.markdown(f'<h1><img src="data:image/png;base64,{flag}" style="height:0.75em;'
                f'vertical-align:baseline;margin-right:0.35em;box-shadow:0 0 0 1px #ddd"'
                f' alt="">US Monitor</h1>', unsafe_allow_html=True)
    st.caption("Rates · market prices · dollar · inflation · activity · fiscal — through the "
               "lens of the Fed's dual mandate.")
    r_star, rho, measure = sidebar()
    if not store.has_data():
        if data.can_refresh():
            st.info("No data yet. Click **↻ Refresh all data** in the sidebar (≈6 min, once).")
        else:
            st.error("No data and no FRED_API_KEY: put your keys in `.env` (see `.env.example`) "
                     "and reload the page.")
        st.stop()
    tabs = st.tabs(["Overview", "Fed Speakers", "Inflation", "Labor", "Activity", "Rates",
                    "Credit & Risk", "Dollar & FX", "Money & Liquidity", "Fiscal", "Policy Rules"])
    with tabs[0]:
        with ui.tab_frame("Overview"):
            overview.render(r_star, rho, measure)
    with tabs[1]:
        fedspeak.render()
    with tabs[2]:
        with ui.tab_frame("Inflation"):
            inflation.render()
    with tabs[3]:
        with ui.tab_frame("Labor"):
            labor.render()
    with tabs[4]:
        with ui.tab_frame("Activity"):
            activity.render()
    with tabs[5]:
        with ui.tab_frame("Rates"):
            rates.render()
    with tabs[6]:
        with ui.tab_frame("Credit & Risk"):
            credit.render()
    with tabs[7]:
        with ui.tab_frame("Dollar & FX"):
            fx.render()
    with tabs[8]:
        with ui.tab_frame("Money & Liquidity"):
            money.render()
    with tabs[9]:
        with ui.tab_frame("Fiscal"):
            fiscal.render()
    with tabs[10]:
        with ui.tab_frame("Policy Rules"):
            policy.render(r_star, rho, measure)


if __name__ == "__main__":
    main()
