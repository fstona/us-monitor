"""Shared Plotly styling so every chart looks like part of one dashboard.

Conventions: clean white template, NBER recession shading, dotted reference
lines, unified hover, legend below the plot. From the Warsh deck: the latest
value of each series goes in its legend label, outliers (e.g. the 2020 spike)
can be clipped by quantile so recent ranges stay legible, and we NEVER use a
dual y-axis — put series with different units side by side instead.

Build charts via these helpers rather than hand-rolling ``go.Figure`` styling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import data

# Consistent, colour-blind-friendly series palette.
PALETTE = ["#1f4e79", "#c00000", "#2e8b57", "#d98c00", "#6a3d9a", "#888888"]
RECESSION = "USREC"  # NBER recession indicator (monthly, 1 = recession)


def fmt_value(v: float, suffix: str = "") -> str:
    a = abs(v)
    s = f"{v:,.0f}" if a >= 1000 else (f"{v:,.1f}" if a >= 100 else f"{v:,.2f}")
    return s + suffix


def base_fig(title: str, yaxis_title: str = "", height: int = 400) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        # Title pinned top-left; legend BELOW the plot so it grows downward
        # and never collides with the title.
        title=dict(text=title, x=0, xanchor="left", font=dict(size=14)),
        height=height,
        margin=dict(l=10, r=10, t=44, b=70),
        yaxis_title=yaxis_title,
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="top", y=-0.16, x=0, xanchor="left"),
        colorway=PALETTE,
    )
    return fig


def _recession_spans(start: str | None) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    rec = data.get_series(RECESSION)
    if start:
        rec = rec[rec.index >= pd.Timestamp(start)]
    spans, run_start, prev = [], None, False
    for date, val in rec.items():
        on = val == 1
        if on and not prev:
            run_start = date
        elif not on and prev:
            spans.append((run_start, date))
        prev = on
    if prev and run_start is not None:
        spans.append((run_start, rec.index[-1]))
    return spans


def add_recession_shading(fig: go.Figure, start: str | None = None) -> None:
    try:
        spans = _recession_spans(start)
    except Exception:  # noqa: BLE001 — shading is cosmetic; never break a chart
        return
    for x0, x1 in spans:
        fig.add_vrect(x0=x0, x1=x1, fillcolor="gray", opacity=0.12, line_width=0)


def add_hline(fig: go.Figure, y: float, text: str, color: str = "gray") -> None:
    fig.add_hline(y=y, line_dash="dot", line_color=color,
                  annotation_text=text, annotation_position="top left")


def clip_yaxis(fig: go.Figure, values: list[np.ndarray], q: float) -> None:
    """Set the y-range to the [q, 1−q] quantiles of the plotted data (+ padding)."""
    arr = np.concatenate([v[~np.isnan(v)] for v in values if len(v)]) if values else np.array([])
    if not arr.size:
        return
    lo, hi = np.quantile(arr, q), np.quantile(arr, 1 - q)
    pad = 0.08 * ((hi - lo) or 1.0)
    fig.update_yaxes(range=[lo - pad, hi + pad])


def multiline(
    title: str,
    series_map: dict[str, pd.Series],
    yaxis_title: str = "",
    start: str | None = None,
    hlines: list[tuple[float, str]] | None = None,
    recession: bool = True,
    clip: float | None = None,
    latest_in_legend: bool = True,
    dashed: tuple[str, ...] = (),
    projections: dict[str, pd.Series] | None = None,
) -> go.Figure:
    """Plot several series on one set of axes (the 'integrated' chart).

    ``clip``: quantile to trim from each tail of the y-range (e.g. 0.02).
    ``dashed``: labels to draw dashed (e.g. a nowcast or a scenario).
    ``projections``: label → 2-point series (last actual, projected) drawn as a
    dotted extension in the same colour (used for the PCE nowcast).
    """
    fig = base_fig(title, yaxis_title)
    suffix = "%" if "%" in yaxis_title else ""
    plotted = []
    for label, s in series_map.items():
        s = s.dropna()
        if start:
            s = s[s.index >= pd.Timestamp(start)]
        if s.empty:
            continue
        name = f"{label}: {fmt_value(float(s.iloc[-1]), suffix)}" if latest_in_legend else label
        color = PALETTE[len(plotted) % len(PALETTE)]
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=name,
                                 line=dict(color=color, dash="dash" if label in dashed else None)))
        plotted.append(s.to_numpy(dtype="float64"))
        p = (projections or {}).get(label)
        if p is not None and len(p) == 2 and p.notna().all():
            fig.add_trace(go.Scatter(
                x=p.index, y=p.values, mode="lines+markers", showlegend=True,
                name=f"{label} — nowcast {p.index[-1]:%b}: {fmt_value(float(p.iloc[-1]), suffix)}",
                line=dict(color=color, dash="dot", width=2),
                marker=dict(symbol=["circle", "circle-open"], size=[0, 10], color=color,
                            line=dict(width=2, color=color))))
    if recession:
        add_recession_shading(fig, start)
    for y, txt in (hlines or []):
        add_hline(fig, y, txt)
    if clip:
        clip_yaxis(fig, plotted, clip)
    return fig


def bars(title: str, s: pd.Series, yaxis_title: str = "", start: str | None = None,
         avg_window: int | None = None, avg_label: str = "", clip: float | None = None,
         hlines: list[tuple[float, str]] | None = None) -> go.Figure:
    """Single-series bar chart (e.g. payroll changes), optional moving-average line."""
    fig = base_fig(title, yaxis_title)
    s = s.dropna()
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    colors = np.where(s.values >= 0, PALETTE[0], PALETTE[1])
    fig.add_trace(go.Bar(x=s.index, y=s.values, marker_color=colors,
                         name=f"{title.split(' —')[0]}: {fmt_value(float(s.iloc[-1]))}"))
    if avg_window:
        ma = s.rolling(avg_window).mean()
        fig.add_trace(go.Scatter(x=ma.index, y=ma.values, mode="lines",
                                 name=f"{avg_label}: {fmt_value(float(ma.iloc[-1]))}",
                                 line=dict(color="black", width=2)))
    for y, txt in (hlines or []):
        add_hline(fig, y, txt)
    if clip:
        clip_yaxis(fig, [s.to_numpy(dtype="float64")], clip)
    return fig


def stacked_bar(title: str, contributions: pd.DataFrame, total: pd.Series | None = None,
                yaxis_title: str = "", total_label: str = "Total") -> go.Figure:
    """Stacked contribution bars ('relative' mode so negatives stack correctly)."""
    fig = base_fig(title, yaxis_title)
    fig.update_layout(barmode="relative", bargap=0.15)
    for col in contributions.columns:
        fig.add_trace(go.Bar(x=contributions.index, y=contributions[col], name=col))
    if total is not None:
        fig.add_trace(go.Scatter(x=total.index, y=total.values, mode="markers+lines",
                      name=total_label, line=dict(color="black", width=2),
                      marker=dict(size=6)))
    return fig


def categorical_lines(title: str, frame: pd.DataFrame, yaxis_title: str = "") -> go.Figure:
    """One line per column over a categorical x (e.g. yield-curve snapshots)."""
    fig = base_fig(title, yaxis_title)
    fig.update_layout(hovermode="x unified")
    for i, col in enumerate(frame.columns):
        fig.add_trace(go.Scatter(x=list(frame.index), y=frame[col].values, mode="lines+markers",
                                 name=col, line=dict(width=3 if i == 0 else 2,
                                                     dash=None if i == 0 else "dot")))
    return fig
