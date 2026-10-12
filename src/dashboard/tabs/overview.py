"""Overview — one screen to form a view: snapshot by area, rule benchmark,
the Warsh checklist and the latest data releases."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config, data
from src.dashboard import ui
from src.dashboard.tabs import policy
from src.dashboard.ui import WARSH
from src.transform import fiscal, indicators, rates, signals

SIGNAL_LABEL = {1: "🔴 hawkish", -1: "🔵 dovish", 0: "⚪ neutral"}


def snapshot() -> None:
    st.markdown("#### Snapshot")
    r1 = st.columns(5)
    with ui.guard("Rates snapshot"):
        mid, _ = ui.last(ui.ff_mid())
        ui.metric(r1[0], "Fed funds (mid)", mid)
        mkt, _ = ui.last(rates.market_implied_direction(ui.load("DGS2"), ui.ff_mid()))
        ui.metric(r1[1], "2y − FF (market)", mkt, "{:+.2f} pp",
                  help="< 0 ⇒ markets price cuts over ~2 years.")
        ten, _ = ui.last(ui.load("DGS10"))
        ui.metric(r1[2], "10y Treasury", ten, delta=ten - ui.load("DGS10").dropna().iloc[-22],
                  delta_fmt="{:+.2f} 1m", delta_color="off")
    with ui.guard("Inflation snapshot"):
        core, d = ui.last(ui.yoy("PCEPILFE"))
        ui.metric(r1[3], f"Core PCE y/y ({d:%b})", core, delta=core - 2,
                  delta_fmt="{:+.2f} vs 2%", delta_color="inverse")
        trim, _ = ui.last(ui.load("PCETRIM12M159SFRBDAL"))
        ui.metric(r1[4], f"Trimmed-mean PCE {WARSH}", trim, delta=trim - 2,
                  delta_fmt="{:+.2f} vs 2%", delta_color="inverse")

    r2 = st.columns(5)
    with ui.guard("Labor snapshot"):
        u, du = ui.last(ui.load("UNRATE"))
        ui.metric(r2[0], f"Unemployment ({du:%b})", u, "{:.1f}%",
                  delta=u - ui.value_asof("NROU", du), delta_fmt="{:+.1f} vs u*", delta_color="off")
    with ui.guard("Activity snapshot"):
        p, dp = ui.last(ui.yoy("LB0000031Q020SBEA"))
        ui.metric(r2[1], f"PDFP 4Q ({dp.year}Q{dp.quarter}) {WARSH}", p, "{:.1f}%")
        now, _ = ui.last(ui.load("GDPNOW"))
        ui.metric(r2[2], "GDPNow", now, "{:.1f}%")
    with ui.guard("Dollar snapshot"):
        usd = ui.load("DTWEXBGS")
        ui.metric(r2[3], "Broad dollar", float(usd.dropna().iloc[-1]), "{:.1f}",
                  delta=indicators.change_over(usd, pd.DateOffset(months=3)),
                  delta_fmt="{:+.1f}% 3m", delta_color="off")
    with ui.guard("Fiscal snapshot"):
        bal, _ = ui.last(fiscal.balance_12m_pct_gdp(ui.load("MTSDS133FMS"), ui.load("GDP")))
        ui.metric(r2[4], "Budget balance 12m", bal, "{:+.1f}% GDP")


def rules_read(r_star: float, rho: float, measure: str) -> None:
    st.markdown("#### What should the Fed do? — rule benchmark")
    with ui.guard("Policy rules"):
        rx = policy.current_prescriptions(r_star, rho, measure)
        c = st.columns(3)
        for col, (name, val) in zip(c, [("Taylor (1993)", rx.taylor),
                                        ("Balanced approach", rx.balanced),
                                        ("Inertial", rx.inertial)]):
            ui.metric(col, name, val, delta=val - rx.current_rate,
                      delta_fmt="{:+.2f} vs now", delta_color="off")
        st.caption(f"Gauge: {measure}; r* = {r_star:.2f}% (sidebar). Positive = rule wants a "
                   "higher rate than today.")


def warsh_checklist() -> None:
    st.markdown(f"#### {WARSH} The Warsh checklist — Jackson Hole 2026 criteria")
    with ui.guard("Warsh checklist"):
        df = signals.checklist_frame(signals.warsh_checklist(ui.load))
        hawk, dove = int((df["_signal"] == 1).sum()), int((df["_signal"] == -1).sum())
        c = st.columns(3)
        c[0].metric("Hawkish", hawk)
        c[1].metric("Dovish", dove)
        c[2].metric("Tilt", "Hawkish" if hawk > dove else ("Dovish" if dove > hawk else "Balanced"))
        st.dataframe(df.drop(columns="_signal"), hide_index=True, width="stretch")
        st.caption("“I stand here today committed to a discipline, not to a decision.” Each row "
                   "maps a criterion from the keynote to the latest data. Thresholds are judgment "
                   "calls kept in transform/signals.py (THRESHOLDS).")


# --- Release feed + scorecard ------------------------------------------------
def _fmt(v, transform, units) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if transform in ("yoy", "ann3m", "ann6m") or (units or "").strip() in ("%", "% 12-mo"):
        return f"{v:.2f}%"
    if transform == "mom_diff":
        return f"{v:+,.0f}k" if "thousand" in (units or "") else f"{v:+,.0f}"
    if "thousand" in (units or ""):
        return f"{v:,.0f}k"
    return f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"


def _fmt_chg(chg, transform, units) -> str:
    if chg is None or pd.isna(chg):
        return "—"
    pct = transform in ("yoy", "ann3m", "ann6m") or "%" in (units or "")
    if pct:
        return f"{chg:+.2f}"
    return f"{chg:+,.0f}k" if "thousand" in (units or "") else f"{chg:+,.0f}"


def _release_stamps() -> dict[str, pd.Timestamp]:
    """Source release stamps (ingestion job + per-tab refreshes)."""
    info = data.release_info()
    return info["last_updated"].dropna().to_dict() if "last_updated" in info else {}


@st.cache_data(ttl=60 * 30, show_spinner=False)
def headline_df() -> pd.DataFrame:
    stamps = _release_stamps()
    rows = []
    for sid, name, sign in config.HEADLINE_RELEASES:
        spec = config.SERIES_BY_ID[sid]
        try:
            disp = indicators.apply_transform(ui.load(sid), spec.transform, spec.freq).dropna()
        except Exception:  # noqa: BLE001
            continue
        dv = float(disp.iloc[-1])
        chg = dv - float(disp.iloc[-2]) if len(disp) > 1 else None
        signal = 0 if (chg is None or abs(chg) < 1e-9) else (1 if (chg > 0) == (sign > 0) else -1)
        lu = stamps.get(sid, pd.NaT)
        rows.append({
            "Category": config.BLOCK_NAMES.get(spec.block, spec.block.title()),
            "Indicator": name,
            "Period": f"{disp.index[-1].year}Q{disp.index[-1].quarter}" if spec.freq == "Q"
                      else disp.index[-1].strftime("%b %Y"),
            "Latest": _fmt(dv, spec.transform, spec.units),
            "Change": _fmt_chg(chg, spec.transform, spec.units),
            "Signal": SIGNAL_LABEL[signal],
            "Released": "—" if pd.isna(lu) else lu.strftime("%d %b %Y"),
            "_ts": lu if not pd.isna(lu) else pd.Timestamp(disp.index[-1], tz="UTC"),
            "_signal": signal,
        })
    return pd.DataFrame(rows)


def releases() -> None:
    st.markdown("#### 📰 Latest releases — which way are they pushing?")
    with ui.guard("Release scorecard"):
        ui.track(*(sid for sid, _, _ in config.HEADLINE_RELEASES))  # headline_df is cached
        df = headline_df()
        hawk, dove = int((df["_signal"] == 1).sum()), int((df["_signal"] == -1).sum())
        feed = df.sort_values("_ts", ascending=False).head(8)
        st.dataframe(feed[["Released", "Indicator", "Period", "Latest", "Change", "Signal"]],
                     hide_index=True, width="stretch")
        c = st.columns(3)
        c[0].metric("Hawkish prints", hawk)
        c[1].metric("Dovish prints", dove)
        c[2].metric("Net data tilt",
                    "Hawkish" if hawk > dove else ("Dovish" if dove > hawk else "Balanced"))
        with st.expander("Full hawkish/dovish scorecard", expanded=False):
            st.dataframe(df.sort_values(["Category", "Indicator"])[
                ["Category", "Indicator", "Period", "Latest", "Change", "Signal", "Released"]],
                hide_index=True, width="stretch")
        st.caption("Signal = direction of the latest change in the headline transform vs the "
                   "prior print. 'Released' = FRED last-updated stamp (from the ingestion job or "
                   "a tab's refresh button); without it, the feed sorts by data period.")


def render(r_star: float, rho: float, measure: str) -> None:
    snapshot()
    st.divider()
    left, right = st.columns([1, 1])
    with left:
        rules_read(r_star, rho, measure)
    with right:
        releases()
    st.divider()
    warsh_checklist()
