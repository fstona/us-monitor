"""PCE nowcast inside the Inflation tab: summary section + projections on the PCE charts.

Reads only the saved runs (store table ``nowcast_runs``) and the backtest metrics
(reference/nowcast_backtest_metrics.csv). It recomputes nothing: the Inflation tab's
refresh button (and "Refresh all data") does that when new CPI/PPI/PCE data appear.
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config
from src.dashboard import charts, ui
from src.nowcast import run as nowcast_run
from src.transform import indicators

BLOCK_LABELS = {"core_goods": "Core goods", "housing": "Housing", "health": "Health care",
                "core_services": "Other core services", "food": "Food", "energy": "Energy"}
LEVEL_ID = {"core": "PCEPILFE", "headline": "PCEPI"}


def current() -> pd.Series | None:
    """Latest run if its target month is still unpublished; None otherwise."""
    h = nowcast_run.runs()
    if h.empty:
        return None
    r = h.iloc[-1]
    ui.track(*LEVEL_ID.values())
    if pd.Timestamp(r.target) <= ui.load("PCEPI").index.max():
        return None                                   # PCE for that month is out: nowcast closed
    return r


def projection(agg: str, transform: str, r: pd.Series | None) -> pd.Series | None:
    """2-point series (last actual, nowcast) for a chart line built from PCE levels."""
    if r is None:
        return None
    s = ui.load(LEVEL_ID[agg]).copy()
    s.loc[pd.Timestamp(r.target)] = s.iloc[-1] * (1 + float(r[f"{agg}_mm"]) / 100)
    f = {"yoy": lambda x: indicators.yoy(x, 12), "ann6": lambda x: indicators.annualized(x, 6, "M"),
         "ann3": lambda x: indicators.annualized(x, 3, "M")}[transform]
    return f(s).iloc[-2:]


def _metrics(stage: int) -> pd.DataFrame:
    m = pd.read_csv(config.PROJECT_ROOT / "reference" / "nowcast_backtest_metrics.csv")
    return m[(m["stage"] == stage) & m["sample"].str.contains("ex Covid")].set_index("aggregate")


def path_chart(target: pd.Timestamp):
    """The nowcast after each release (last PCE → CPI/PPI), with ± backtest RMSFE of
    each stage."""
    h = nowcast_run.runs()
    h = h[pd.to_datetime(h.target) == target].copy()
    when = pd.to_datetime(h.event_date, utc=True).dt.tz_convert(ui.TZ)
    h["x"] = [f"{ev.replace(' released', '')}<br>{d:%d %b}" for ev, d in zip(h.event, when)]  # one slot per release
    m = pd.read_csv(config.PROJECT_ROOT / "reference" / "nowcast_backtest_metrics.csv")
    m = m[m["sample"].str.contains("ex Covid")].set_index(["aggregate", "stage"]).rmsfe_bps / 100
    fig = charts.base_fig(f"{target:%b %Y} nowcast after each release (m/m %, ± backtest error)", "%")
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(type="category")
    for i, (agg, name) in enumerate((("core", "Core PCE"), ("headline", "Headline PCE"))):
        err = [float(m.get((agg, int(s)), 0)) for s in h.stage]
        fig.add_trace(go.Scatter(
            x=h.x, y=h[f"{agg}_mm"], mode="lines+markers+text", name=name, line_shape="hv",
            text=[f"{v:+.2f}" for v in h[f"{agg}_mm"]], textposition="top center",
            error_y=dict(type="data", array=err, visible=True, thickness=1, width=4),
            customdata=h.event, hovertemplate="%{customdata}: %{y:+.2f}%<extra>" + name + "</extra>",
            line=dict(color=charts.PALETTE[i])))
    return fig


def section() -> None:
    r = current()
    ui.section("PCE nowcast — next print",
               "Bottom-up bridge: each of the ~220 PCE categories takes its CPI/PPI source "
               "(or a prior if not yet released), weighted by last month's spending. Recomputed "
               "automatically when the tab's refresh brings a new CPI, PPI or PCE.")
    if r is None:
        st.info("No open nowcast yet — click **↻ Refresh this tab** above to compute it.")
        return
    stage = int(r.stage)
    met = _metrics(stage)
    c = st.columns(4)
    for col, agg, name in ((c[0], "core", "Core PCE"), (c[1], "headline", "Headline PCE")):
        ui.metric(col, f"{name} {pd.Timestamp(r.target):%b %Y} (m/m)", float(r[f"{agg}_mm"]), "{:+.2f}%",
                  delta=float(r[f"{agg}_yoy"]), delta_fmt="{:.2f}% y/y implied", delta_color="off")
    c[2].metric("Stage", r.stage_name, f"updated {pd.Timestamp(r.run_at).tz_convert(ui.TZ):%d %b %H:%M}",
                delta_color="off")
    if "core" in met.index:
        m = met.loc["core"]
        c[3].metric("Backtest error, core", f"±{m.rmsfe_bps:.1f} bps",
                    f"R² {m.r2:.2f} · {m.hit5:.0%} within ±5 bps", delta_color="off",
                    help="RMSFE of this stage in a pseudo real-time backtest vs the FIRST print, "
                         "2015+, ex Covid 2020-21. "
                         "Headline: " + (f"±{met.loc['headline'].rmsfe_bps:.1f} bps, "
                                         f"R² {met.loc['headline'].r2:.2f}" if "headline" in met.index else "—"))
    c1, c2 = st.columns(2)
    with c1, ui.guard("Nowcast path"):
        ui.plot(path_chart(pd.Timestamp(r.target)))
    with c2, ui.guard("Nowcast contributions"):
        fig = charts.base_fig("Contributions by block (pp of m/m, before bias correction)", "pp")
        fig.update_layout(barmode="relative", hovermode="x unified")
        blocks = {agg: json.loads(r[f"{agg}_blocks"]) for agg in ("core", "headline")}
        for key, label in BLOCK_LABELS.items():
            fig.add_trace(go.Bar(x=["Core PCE", "Headline PCE"], name=label,
                                 y=[blocks["core"].get(key, 0.0), blocks["headline"].get(key, 0.0)]))
        ui.plot(fig)
    st.caption("Projections are drawn dotted on the PCE charts below.")
