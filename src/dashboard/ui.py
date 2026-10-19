"""Shared dashboard helpers: cached data access, the global lookback,
per-chart error isolation, and the per-tab frame (refresh button + data
freshness on top, table of the series used at the bottom). Every tab module
imports from here.

Series tracking: ``load()`` records each series ID it is asked for into the
tab currently being rendered (see ``tab_frame``), so tabs never list their
series by hand. Code that reads data through another cached function must
call ``track()`` with the IDs it uses (a cache hit skips the inner loads).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config, data
from src.nowcast import run as nowcast_run
from src.transform import indicators, labor, rates

TARGET = [(config.INFLATION_TARGET, "2% target")]
ZERO = [(0.0, "")]
WARSH = "★"  # marks analyses drawn from Warsh's Jackson Hole 2026 keynote


# --- Series tracking ---------------------------------------------------------
_rec = threading.local()   # one Streamlit script run per thread


def track(*series_ids: str) -> None:
    ids = getattr(_rec, "ids", None)
    if ids is not None:
        ids.update(series_ids)


# --- Cached data access ----------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def _load_cached(series_id: str) -> pd.Series:
    return data.get_series(series_id)


def load(series_id: str) -> pd.Series:
    track(series_id)
    return _load_cached(series_id)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _labor_frame_cached() -> pd.DataFrame:
    return labor.labor_market_frame()


def labor_frame() -> pd.DataFrame:
    track(*labor.INPUTS)
    return _labor_frame_cached()


def yoy(series_id: str) -> pd.Series:
    """y/y % change using the catalog's native frequency."""
    freq = config.SERIES_BY_ID[series_id].freq
    return indicators.yoy(load(series_id), indicators.PER_YEAR.get(freq, 12))


def ann(series_id: str, window: int) -> pd.Series:
    freq = config.SERIES_BY_ID[series_id].freq
    return indicators.annualized(load(series_id), window, freq)


def monthly(series_id: str, how: str = "last") -> pd.Series:
    return indicators.to_monthly(load(series_id), how)


def ff_mid() -> pd.Series:
    """Daily fed funds target midpoint."""
    return rates.target_midpoint(load("DFEDTARU"), load("DFEDTARL"))


def ff_mid_monthly() -> pd.Series:
    """Monthly policy rate: target midpoint (2008-12+) spliced onto EFFR before."""
    mid = indicators.to_monthly(ff_mid())
    effr = load("FEDFUNDS")
    return pd.concat([effr[effr.index < mid.index[0]], mid]).sort_index()


def last(s: pd.Series) -> tuple[float, pd.Timestamp]:
    s = s.dropna()
    return float(s.iloc[-1]), s.index[-1]


def value_asof(series_id: str, date) -> float:
    """Point-in-time value. Use for CBO series (NROU, GDPPOT) that run to ~2036
    — ``.iloc[-1]`` would grab a projection, not today's value."""
    return float(load(series_id).asof(pd.Timestamp(date)))


# --- Lookback --------------------------------------------------------------
def since(years: int | None = None) -> str:
    """Chart start date: the sidebar lookback unless a tab forces ``years``."""
    n = years if years is not None else st.session_state.get("lookback_years", 10)
    return str((pd.Timestamp.today() - pd.DateOffset(years=n)).date())


# --- Rendering -------------------------------------------------------------
def plot(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True)  # `width=` not yet supported for plotly in 1.50


@contextmanager
def guard(what: str):
    """Isolate a chart/section: a bad series warns locally, the tab survives."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        st.warning(f"{what} could not be built: {exc}")


def section(title: str, caption: str | None = None) -> None:
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)


def metric(col, label: str, value: float | None, fmt: str = "{:.2f}%",
           delta: float | None = None, delta_fmt: str = "{:+.2f}",
           help: str | None = None, delta_color: str = "normal") -> None:
    if value is None or pd.isna(value):
        col.metric(label, "—", help=help)
        return
    col.metric(label, fmt.format(value),
               None if delta is None or pd.isna(delta) else delta_fmt.format(delta),
               help=help, delta_color=delta_color)


# --- Tab frame: refresh + freshness (top) and series table (bottom) ------------
TZ = "America/Sao_Paulo"
_FREQ = {"D": "Daily", "W": "Weekly", "M": "Monthly", "Q": "Quarterly", "A": "Annual"}


def _period(ts: pd.Timestamp, freq: str) -> str:
    if freq == "Q":
        return f"{ts.year}Q{ts.quarter}"
    if freq == "M":
        return f"{ts:%b %Y}"
    if freq == "A":
        return f"{ts.year}"
    return f"{ts:%d %b %Y}"


def _local(ts) -> str:
    return "—" if ts is None or pd.isna(ts) else f"{pd.Timestamp(ts).tz_convert(TZ):%d %b %Y %H:%M}"


def series_status(series_ids: list[str]) -> pd.DataFrame:
    info = data.release_info()
    rows = []
    for sid in series_ids:
        spec = config.SERIES_BY_ID.get(sid)
        if spec is None or spec.block == "reference":
            continue
        try:
            s = _load_cached(sid).dropna()
            today = pd.Timestamp.today()
            # CBO series run years ahead: the "latest" relevant point is today's.
            s = s[s.index <= today] if spec.id in ("NROU", "GDPPOT") else s
            last_obs = _period(s.index[-1], spec.freq) if len(s) else "—"
        except Exception:  # noqa: BLE001
            last_obs = "unavailable"
        released = info["last_updated"].get(sid) if "last_updated" in info else None
        rows.append({
            "Series": spec.label, "ID": sid, "Source": spec.source.upper(),
            "Frequency": _FREQ.get(spec.freq, spec.freq),
            "Latest observation": last_obs,
            "Released (source)": _local(released),
            "Fetched": _local(data.fetched_at(sid)),
        })
    return pd.DataFrame(rows)


def refresh_all() -> None:
    """Sidebar button: every catalog series + nowcast inputs + Fed-speak, one pass."""
    from src.jobs import fedspeak
    ids = [s.id for s in config.SERIES] + nowcast_run.FRED_INPUTS
    bar = st.sidebar.progress(0.0, text="Refreshing all data…")
    res = data.refresh(ids, progress=lambda i, n, sid: bar.progress(i / n, text=f"{sid} ({i + 1}/{n})"))
    bar.progress(1.0, text="Fed speakers…")
    fedspeak.run()
    bar.progress(1.0, text="PCE nowcast…")
    nowcast_msg = nowcast_run.safe_update(refresh_inputs=False)
    bar.empty()
    st.cache_data.clear()
    st.session_state["_refresh_all_msg"] = f"{res.summary()}. Fed speakers updated. {nowcast_msg}"
    st.rerun()


def _refresh(name: str, ids: list[str]) -> None:
    nowcast = name == "Inflation"           # new CPI/PPI/PCE → the nowcast recomputes itself
    if nowcast:
        ids = ids + nowcast_run.FRED_INPUTS  # one pass: the nowcast reuses what is downloaded here
    bar = st.progress(0.0, text=f"Refreshing {name}…")
    res = data.refresh(ids, progress=lambda i, n, sid: bar.progress(
        i / n, text=f"Refreshing {name}: {sid} ({i + 1}/{n})"))
    extra = ""
    if nowcast:
        bar.progress(1.0, text="PCE nowcast…")
        extra = " " + nowcast_run.safe_update(refresh_inputs=False)
    bar.empty()
    st.cache_data.clear()
    st.session_state[f"_refresh_msg_{name}"] = res.summary() + "." + extra
    st.rerun()


def tab_header(name: str, ids: list[str]) -> None:
    fetched = [t for t in (data.fetched_at(i) for i in ids
                           if config.SERIES_BY_ID.get(i) and
                           config.SERIES_BY_ID[i].block != "reference") if t is not None]
    c = st.columns([5, 1.4])
    if fetched:
        oldest, newest = min(fetched), max(fetched)
        span = (_local(newest) if newest - oldest < pd.Timedelta(minutes=5)
                else f"{_local(oldest)} → {_local(newest)}")
        c[0].caption(f"🕒 Data fetched: **{span}** (BRT) · {len(fetched)} series · "
                     "release dates and latest observations in the table at the bottom of the tab")
    msg = st.session_state.pop(f"_refresh_msg_{name}", None)
    if msg:
        c[0].success(msg)
    if data.can_refresh() and c[1].button(
            "↻ Refresh this tab", key=f"refresh_{name}",
            help=f"Check the {len(ids)} series used here and download only those with new data. "
                 "If a download fails, the previous data is kept."):
        _refresh(name, ids)


def tab_footer(ids: list[str]) -> None:
    st.divider()
    with st.expander(f"📋 Series in this tab ({len(ids)}) — latest observation and release",
                     expanded=False):
        df = series_status(ids)
        if df.empty:
            st.caption("No catalog series used here.")
            return
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption("Latest observation = the period the charts above are using. Released = the "
                   "source's last-updated stamp (FRED), recorded when the series is refreshed. Fetched = when the data was "
                   "downloaded. Times in BRT.")


@contextmanager
def tab_frame(name: str):
    """Wrap a tab's ``render()``: records the series it loads, then fills the
    header (reserved at the top before rendering) and appends the footer."""
    top = st.container()
    _rec.ids = set()
    try:
        yield
    finally:
        ids = sorted(_rec.ids)
        _rec.ids = None
    with top:
        tab_header(name, ids)
    tab_footer(ids)
