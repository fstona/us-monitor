"""Fed Speakers — who votes, what they said lately (tone + summary), who speaks next."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data, store
from src.ingest import llm
from src.dashboard import charts, ui
from src.transform import fomc

TONE_COLORS = {"Dovish": "#1f4e9c", "Lean dovish": "#6a8fd0", "Neutral": "#8a8a8a",
               "Lean hawkish": "#e07a7a", "Hawkish": "#c00000",
               "Not about policy": "#b0b0b0", "No transcript": "#b0b0b0"}
TONE_WINDOW_DAYS = 90


@st.cache_data(ttl=10 * 60, show_spinner=False)
def table(name: str) -> pd.DataFrame:
    return store.get_table(name)


def _badge(label: str, score: float | None = None) -> str:
    color = TONE_COLORS.get(label, "#8a8a8a")
    txt = label if score is None or pd.isna(score) else f"{label} {score:+.1f}"
    return (f'<span style="background:{color};color:#fff;border-radius:10px;padding:1px 8px;'
            f'font-size:0.78em;white-space:nowrap">{html.escape(txt)}</span>')


def _bar(v: float | None, scale: float = 1.0) -> str:
    """Diverging bar centred on 0: blue = dovish (left), red = hawkish (right)."""
    if v is None or pd.isna(v):
        return '<span style="color:#aaa">—</span>'
    w = min(abs(v) / scale, 1.0) * 50
    side = (f"right:50%;width:{w:.0f}%;background:linear-gradient(to left,#1f4e9c,#9db5e0)"
            if v < 0 else f"left:50%;width:{w:.0f}%;background:linear-gradient(to right,#e8a0a0,#c00000)")
    return ('<div style="position:relative;height:14px;min-width:110px;background:#f3f3f3">'
            f'<div style="position:absolute;top:0;bottom:0;{side}"></div>'
            '<div style="position:absolute;left:50%;top:-2px;bottom:-2px;border-left:1px dashed #333">'
            '</div></div>')


def _voter_mark(v: bool) -> str:
    return ('<span style="color:#2e7d32;font-weight:700">✓</span>' if v
            else '<span style="color:#d32f2f;font-weight:700">✗</span>')


def participants_frame(speeches: pd.DataFrame) -> pd.DataFrame:
    roster = fomc.load_roster()
    year = pd.Timestamp.today().year
    for y in (year, year + 1, year + 2):
        roster[f"v{y}"] = roster["seat"].map(lambda s, y=y: fomc.is_voter(s, y))
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=TONE_WINDOW_DAYS)
    recent = speeches[(speeches["date"] >= cutoff) & speeches["tone_score"].notna()]
    roster["tone_90d"] = roster["key"].map(recent.groupby("speaker")["tone_score"].mean())
    roster["n_90d"] = roster["key"].map(recent.groupby("speaker").size()).fillna(0).astype(int)
    last = speeches.sort_values("date").groupby("speaker").tail(1).set_index("speaker")
    roster["last_date"] = roster["key"].map(last["date"])
    roster["last_title"] = roster["key"].map(last["title"])
    roster["last_url"] = roster["key"].map(last["url"])
    roster["last_label"] = roster["key"].map(last["tone_label"])
    return roster


def roster_html(df: pd.DataFrame) -> str:
    year = pd.Timestamp.today().year
    th = 'style="text-align:left;padding:6px 8px;border-bottom:2px solid #333;white-space:nowrap"'
    td = 'style="padding:5px 8px;border-bottom:1px solid #eee;vertical-align:middle"'
    head = (f"<tr><th {th}>Name</th><th {th}>Position</th><th {th}>Hawk scale (ITC)</th>"
            f"<th {th}>Speech tone ({TONE_WINDOW_DAYS}d)</th><th {th}>Latest remarks</th>"
            + "".join(f'<th {th} style="text-align:center">{y}</th>' for y in (year, year + 1, year + 2))
            + "</tr>")
    rows = []
    for r in df.itertuples():
        name = html.escape(r.name) + ("*" if r.interim else "")
        if getattr(r, "seat") == "board":
            pos = html.escape(r.position)
        else:
            pos = html.escape(r.institution)
        if pd.isna(r.last_date):
            last = '<span style="color:#aaa">none in store</span>'
        else:
            last = (f'{r.last_date:%d %b} · <a href="{html.escape(str(r.last_url))}" target="_blank">'
                    f'{html.escape(str(r.last_title))[:60]}</a> {_badge(r.last_label)}')
        tone = _bar(r.tone_90d, 2.0) + (f'<div style="font-size:0.72em;color:#666">'
                                        f'{r.tone_90d:+.2f} · {r.n_90d} speech(es)</div>'
                                        if not pd.isna(r.tone_90d) else "")
        votes = "".join(f'<td {td} align="center">{_voter_mark(getattr(r, f"v{y}"))}</td>'
                        for y in (year, year + 1, year + 2))
        rows.append(f"<tr><td {td}><b>{name}</b></td><td {td}>{pos}</td>"
                    f"<td {td}>{_bar(r.hawk_itc, 1.0)}</td><td {td}>{tone}</td>"
                    f"<td {td}><span style=\"font-size:0.85em\">{last}</span></td>{votes}</tr>")
    band = ('<tr><td colspan="8" style="background:#e6efe0;font-weight:700;padding:3px 8px">'
            '{}</td></tr>')
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;'
            'font-size:0.92em">' + head + band.format("Most dovish") + "".join(rows)
            + band.format("Most hawkish") + "</table></div>")


def _span(a: pd.Timestamp, b: pd.Timestamp) -> str:
    """'27–28 Oct', or '30 Apr–1 May' when the span crosses a month."""
    return f"{a:%d}–{b:%d %b}" if a.month == b.month else f"{a:%d %b}–{b:%d %b}"


def header(meetings: pd.DataFrame, status: pd.DataFrame | None) -> None:
    today = pd.Timestamp.today().normalize()
    info = fomc.blackout_status(list(zip(meetings["start"], meetings["end"])), today)
    c = st.columns([2, 2, 3])
    if info:
        c[0].metric("Next FOMC meeting",
                    _span(info["meeting_start"], info["meeting_end"]),
                    f"in {(info['meeting_start'] - today).days} days", delta_color="off")
        c[1].metric("Blackout", _span(info["blackout_start"], info["blackout_end"]),
                    "IN BLACKOUT" if info["in_blackout"] else f"starts in {info['days_to_blackout']} days",
                    delta_color="inverse" if info["in_blackout"] else "off")
        if info["in_blackout"]:
            st.warning("📵 FOMC blackout: participants do not comment on monetary policy until "
                       f"{info['blackout_end']:%d %b}.")
    if status is not None and not status.empty:
        s = status.iloc[0]
        method = {"claude": "Claude (Opus 5.5)", "lexicon": "hawk/dove lexicon"}[s["method"]]
        c[2].caption(f"🕒 Data fetched: **{pd.Timestamp(s['run_at']).tz_convert('America/Sao_Paulo'):%d %b %Y %H:%M}** "
                     f"(BRT) · tone by **{method}** · {s['n_speeches']} remarks in store · "
                     "sources table at the bottom of the tab"
                     + (f" · ⚠️ {s['errors']}" if s["errors"] else ""))
    if data.can_refresh() and c[2].button("↻ Refresh this tab", help="Fetch new speeches, "
                                                 "calendar and FOMC dates (≈1 min)"):
        from src.jobs import fedspeak as job
        with st.spinner("Fetching speeches and calendar…"):
            job.run()
        table.clear()
        st.rerun()


def calendar_section(cal: pd.DataFrame, roster: pd.DataFrame, meetings: pd.DataFrame) -> None:
    today = pd.Timestamp.today().normalize()
    nxt = cal[(cal["date"] >= today) & (cal["date"] <= today + pd.Timedelta(days=7))].copy()
    st.markdown("#### 🗓️ Next 7 days")
    info = fomc.blackout_status(list(zip(meetings["start"], meetings["end"])), today)
    if nxt.empty:
        st.info("No scheduled appearances found for the next 7 days.")
    else:
        names = roster.set_index("key")
        year = today.year

        def who(k):
            if not k or k not in names.index:
                return "—"
            r = names.loc[k]
            vote = "voter" if fomc.is_voter(r["seat"], year) else "non-voter"
            return f"{r['name']} ({r['position'] if r['seat'] == 'board' else r['institution']}, {vote})"

        nxt["_t"] = pd.to_datetime(nxt["time_et"].str.replace(".", "", regex=False).str.upper(),
                                   format="%I:%M %p", errors="coerce")
        nxt = nxt.sort_values(["date", "_t"])
        nxt["Who"] = nxt["speaker"].map(who)
        nxt["Day"] = nxt["date"].dt.strftime("%a %d %b")
        if info:
            nxt["Blackout"] = nxt["date"].between(info["blackout_start"], info["blackout_end"]).map(
                {True: "📵", False: ""})
        nxt = nxt.rename(columns={"time_et": "Time (ET)", "event": "Event", "topic": "Topic",
                                  "location": "Where", "link": "Link", "source": "Source"})
        cols = ["Day", "Time (ET)", "Who", "Event", "Topic", "Where", "Link", "Source"]
        if "Blackout" in nxt:
            cols.insert(1, "Blackout")
        st.dataframe(nxt[[c for c in cols if c in nxt]], hide_index=True, width="stretch",
                     column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")})
    st.caption("Coverage: the Board's official calendar (Governors, FOMC, Beige Book) is complete. "
               "Reserve Bank presidents' engagements come from `reference/fedspeak_calendar_manual.csv` "
               "and, when ANTHROPIC_API_KEY is set, a Claude web search of the banks' event pages.")


def remarks_section(speeches: pd.DataFrame, roster: pd.DataFrame) -> None:
    st.markdown("#### 🎙️ Latest remarks")
    names = roster.set_index("key")
    year = pd.Timestamp.today().year
    c = st.columns([3, 1, 1])
    pick = c[0].multiselect("Speakers", list(roster["key"]),
                            format_func=lambda k: names.loc[k, "name"], placeholder="All")
    voters_only = c[1].toggle("Voters only", value=False)
    policy_only = c[2].toggle("Policy only", value=True,
                              help="Hide remarks on supervision, payments, community topics.")
    df = speeches.copy()
    if pick:
        df = df[df["speaker"].isin(pick)]
    if voters_only:
        df = df[df["speaker"].map(lambda k: fomc.is_voter(names.loc[k, "seat"], year))]
    if policy_only:
        df = df[df["about_policy"].fillna(False).astype(bool)]
    for r in df.head(15).itertuples():
        who = names.loc[r.speaker]
        role = who["position"] if who["seat"] == "board" else f"{who['institution']} Fed"
        vote = "voter" if fomc.is_voter(who["seat"], year) else "non-voter"
        st.markdown(
            f"**{r.date:%d %b %Y} · {who['name']}** <span style='color:#666'>({role}, {vote})</span> "
            f"{_badge(r.tone_label, r.tone_score)}<br>"
            f"<a href='{html.escape(r.url)}' target='_blank'>{html.escape(str(r.title))}</a> "
            f"<span style='color:#999;font-size:0.8em'>· {r.source} · tone: {r.tone_method}</span>",
            unsafe_allow_html=True)
        if isinstance(r.summary, str) and r.summary:
            st.caption(r.summary[:700])
    if len(df) > 15:
        st.caption(f"Showing 15 of {len(df)} — narrow with the filters.")


def tone_charts(parts: pd.DataFrame, speeches: pd.DataFrame) -> None:
    c1, c2 = st.columns(2)
    with c1, ui.guard("Tone map"):
        d = parts.dropna(subset=["tone_90d"])
        year = pd.Timestamp.today().year
        fig = charts.base_fig(f"ITC hawk scale vs speech tone ({TONE_WINDOW_DAYS}d)",
                              "speech tone (−2 dove … +2 hawk)")
        fig.update_layout(hovermode="closest")
        for voter, sub in d.groupby(d[f"v{year}"]):
            fig.add_trace(go.Scatter(
                x=sub["hawk_itc"], y=sub["tone_90d"], mode="markers+text", text=sub["name"],
                textposition="top center", name=f"{year} voter" if voter else "non-voter",
                marker=dict(size=11, symbol="circle" if voter else "circle-open")))
        fig.update_xaxes(title="ITC hawk scale (−1 dove … +1 hawk)")
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        fig.add_vline(x=0, line_dash="dot", line_color="gray")
        ui.plot(fig)
        st.caption("Points above their peers on the y-axis are sounding more hawkish lately than "
                   "their reputation (x-axis) suggests.")
    with c2, ui.guard("Committee tone"):
        s = speeches.dropna(subset=["tone_score"]).set_index("date").sort_index()
        roster = fomc.load_roster().set_index("key")
        year = pd.Timestamp.today().year
        s["voter"] = s["speaker"].map(lambda k: fomc.is_voter(roster.loc[k, "seat"], year))
        monthly = {
            "All participants": s["tone_score"].resample("MS").mean(),
            f"{year} voters": s.loc[s["voter"], "tone_score"].resample("MS").mean(),
        }
        ui.plot(charts.multiline("Average speech tone by month", monthly,
                                 "tone (−2 … +2)", hlines=[(0.0, "neutral")], recession=False))


SOURCE_COVERS = {
    "Board": "Governors (full speech list, JSON)", "BIS": "Reserve Bank presidents (aggregator)",
    "NY Fed": "Williams", "Boston Fed": "Collins", "Philadelphia Fed": "Paulson",
    "Cleveland Fed": "Hammack", "Richmond Fed": "Barkin", "Atlanta Fed": "Venable",
    "Chicago Fed": "Goolsbee", "Minneapolis Fed": "Kashkari", "Dallas Fed": "Logan",
    "SF Fed": "Daly", "St. Louis Fed": "Musalem — blocked to scripts; web search/manual only",
    "Kansas City Fed": "Schmid — blocked to scripts; web search/manual only",
    "Web search": "Claude web search (needs ANTHROPIC_API_KEY)", "Manual": "reference/*_manual.csv",
}


def sources_footer(speeches: pd.DataFrame, cal: pd.DataFrame, meetings: pd.DataFrame,
                   status: pd.DataFrame | None) -> None:
    st.divider()
    with st.expander("📋 Sources in this tab — latest item and status", expanded=False):
        g = speeches.groupby("source").agg(latest=("date", "max"), items=("url", "size"))
        errors = str(status.iloc[0]["errors"]) if status is not None and not status.empty else ""
        rows = []
        for src, covers in SOURCE_COVERS.items():
            key = src.replace(" Fed", "").replace("NY", "New York").replace("SF", "San Francisco")
            err = next((e for e in errors.split("; ") if e.startswith(f"{key}:")), "")
            rows.append({
                "Source": src, "Covers": covers,
                "Latest remark in store": f"{g.loc[src, 'latest']:%d %b %Y}" if src in g.index else "—",
                "Remarks (180d)": int(g.loc[src, "items"]) if src in g.index else 0,
                "Status": (f"⚠️ {err}" if err
                           else "—" if src in ("St. Louis Fed", "Kansas City Fed")
                           else "off (no ANTHROPIC_API_KEY)" if src == "Web search" and not llm.available()
                           else "ok"),
            })
        cal_latest = cal.groupby("source")["date"].max()
        for src, d in cal_latest.items():
            rows.append({"Source": f"Calendar: {src}", "Covers": "Scheduled appearances",
                         "Latest remark in store": f"furthest event {d:%d %b %Y}",
                         "Remarks (180d)": int((cal["source"] == src).sum()), "Status": "ok"})
        rows.append({"Source": "FOMC meeting calendar", "Covers": "Meeting dates → blackout",
                     "Latest remark in store": f"through {meetings['end'].max():%b %Y}",
                     "Remarks (180d)": len(meetings), "Status": "ok"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if status is not None and not status.empty:
            st.caption(f"Last refresh: {pd.Timestamp(status.iloc[0]['run_at']).tz_convert('America/Sao_Paulo'):%d %b %Y %H:%M} (BRT).")


def render() -> None:
    st.subheader("Fed speakers — who votes, what they are saying, who speaks next")
    try:
        speeches = table("fedspeak_speeches")
        cal = table("fedspeak_calendar")
        meetings = table("fomc_meetings")
    except FileNotFoundError:
        st.info("No Fed-speak data yet — use **↻ Refresh all data** in the sidebar.")
        return
    try:
        status = table("fedspeak_status")
    except FileNotFoundError:
        status = None
    speeches = speeches.assign(date=pd.to_datetime(speeches["date"]))
    cal = cal.assign(date=pd.to_datetime(cal["date"]))

    with ui.guard("Header"):
        header(meetings, status)

    with ui.guard("Participants"):
        parts = participants_frame(speeches)
        st.markdown("#### 👥 FOMC participants")
        order = st.radio("Order by", ["ITC hawk scale", "Speech tone (90d)"], horizontal=True)
        key = "hawk_itc" if order == "ITC hawk scale" else "tone_90d"
        st.markdown(roster_html(parts.sort_values(key, na_position="last")), unsafe_allow_html=True)
        st.caption("Hawk scale: [ITC Markets Research, *FOMC – ITC Hawk/Dove Analysis*, 14 Sep 2026]"
                   "(https://www.itcmarkets.com/wp-content/uploads/2020/02/FOMC-76.png) — values read "
                   "from the published chart; edit `reference/fomc_roster.csv`. Speech tone: average score of this "
                   f"participant's policy remarks in the last {TONE_WINDOW_DAYS} days. Voting follows "
                   "the statutory rotation (computed, not typed). * interim president.")

    with ui.guard("Calendar"):
        calendar_section(cal, parts, meetings)
    with ui.guard("Remarks"):
        remarks_section(speeches, parts)
    tone_charts(parts, speeches)
    st.caption("Tone method: with ANTHROPIC_API_KEY set, Claude reads each transcript and scores "
               "the speaker's own policy view; otherwise a transparent hawk/dove phrase lexicon "
               "(transform/fedspeak.py) — crude: it misses negations and conditionals, so open the "
               "speech before concluding. Lexicon scores compare speakers better than they "
               "measure absolute tone.")
    with ui.guard("Sources"):
        sources_footer(speeches, cal, meetings, status)
