"""Warsh checklist — the Jackson Hole 2026 ("In Our Time") criteria as signals.

Each check reads the latest data and classifies it as hawkish (+1, argues for
tighter / higher-for-longer), neutral (0) or dovish (−1, room to ease), with
the benchmark the Chair himself used where he gave one.

Thresholds are JUDGMENT CALLS, kept together in ``THRESHOLDS`` so they are easy
to review and tune — they are not estimated.

All functions take ``get``: a callable ``series_id -> pd.Series`` (the
dashboard passes its cached loader), so this module stays I/O-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from src import config
from src.transform import indicators

Getter = Callable[[str], pd.Series]

THRESHOLDS = {
    # underlying inflation (trimmed-mean PCE, %)
    "trim_6m_hawk": 2.5, "trim_6m_dove": 2.2,
    # breadth: % of PCE components rising > 3% (y/y)
    "diff_hawk": 45.0, "diff_dove": 36.0,
    # expectations
    "fwd5y5y_hawk": 2.6, "mich1y_hawk": 4.0,
    # commodities (PPI all commodities, y/y %)
    "ppi_hawk": 5.0, "ppi_dove": 0.0,
    # PDFP (4-quarter growth, %)
    "pdfp_hawk": 3.0, "pdfp_dove": 1.5,
    # financial conditions
    "nfci_hawk": -0.40, "nfci_dove": 0.0,          # below 0 = looser than average
    "hy_hawk": 3.0, "hy_dove": 5.0,                # HY OAS, %
    "sloos_hawk": 0.0, "sloos_dove": 20.0,         # net % tightening C&I
    # labor
    "claims_hawk": 230_000, "claims_dove": 280_000,  # initial claims, 4-wk avg
    "theta_hawk": 1.2, "theta_dove": 0.8,            # vacancies per unemployed
    # money: M2 y/y vs ~4% nominal growth at 2% inflation
    "m2_hawk": 6.0, "m2_dove": 2.0,
}


@dataclass
class Check:
    area: str
    indicator: str
    reading: str
    benchmark: str
    signal: int        # +1 hawkish, 0 neutral, −1 dovish
    quote: str         # what Warsh said about it


def _band(x: float, hawk: float, dove: float) -> int:
    """+1 if x on the hawkish side of ``hawk``, −1 beyond ``dove``, else 0.
    Works whichever direction is hawkish (hawk > dove or hawk < dove)."""
    if hawk >= dove:
        return 1 if x > hawk else (-1 if x < dove else 0)
    return 1 if x < hawk else (-1 if x > dove else 0)


def _last(s: pd.Series) -> tuple[float, pd.Timestamp]:
    s = s.dropna()
    return float(s.iloc[-1]), s.index[-1]


def warsh_checklist(get: Getter) -> list[Check]:
    t = THRESHOLDS
    checks: list[Check] = []

    def add(fn):
        try:
            checks.append(fn())
        except Exception:  # noqa: BLE001 — one missing series must not sink the table
            pass

    def underlying():
        t12, d = _last(get("PCETRIM12M159SFRBDAL"))
        t6, _ = _last(get("PCETRIM6M680SFRBDAL"))
        sig = 1 if (t6 > t["trim_6m_hawk"] or (t12 > t["trim_6m_hawk"] and t6 >= t12)) \
            else (-1 if t6 <= t["trim_6m_dove"] else 0)
        return Check("Inflation", "Trimmed-mean PCE (12m / 6m ann.)",
                     f"{t12:.2f}% / {t6:.2f}% ({d:%b %y})",
                     "2%; 6m below 12m = converging", sig,
                     "Moving to our objective, clearly and at sufficient speed")

    def core6m():
        s = indicators.annualized(get("PCEPILFE"), 6, "M")
        v, d = _last(s)
        return Check("Inflation", "Core PCE (6m ann.)", f"{v:.2f}% ({d:%b %y})",
                     "2% target", _band(v, 2.75, 2.25),
                     "The core measures… are also elevated")

    def breadth():
        v, d = _last(get("BEA_PCE_DIFF12"))
        return Check("Inflation", "PCE components rising > 3% (12m)", f"{v:.0f}% ({d:%b %y})",
                     f"~{config.DIFFUSION_PRE_PANDEMIC:.0f}% pre-pandemic",
                     _band(v, t["diff_hawk"], t["diff_dove"]),
                     "54 percent… showed price increases above 3 percent")

    def expectations():
        f, d = _last(get("T5YIFR"))
        m, _ = _last(get("MICH"))
        sig = 1 if (f > t["fwd5y5y_hawk"] or m > t["mich1y_hawk"]) else 0
        return Check("Inflation", "Expectations: 5y5y BE / UMich 1y",
                     f"{f:.2f}% / {m:.1f}% ({d:%b %y})", "Anchored ≈ 2–2.5%", sig,
                     "They tend to look strong and durable… until they don't")

    def commodities():
        v, d = _last(indicators.yoy(get("PPIACO"), 12))
        return Check("Inflation", "PPI all commodities (y/y)", f"{v:.1f}% ({d:%b %y})",
                     "Upside risk if rising", _band(v, t["ppi_hawk"], t["ppi_dove"]),
                     "The recent rise in overall commodity prices also bears watching")

    def pdfp():
        v, d = _last(indicators.yoy(get("LB0000031Q020SBEA"), 4))
        return Check("Activity", "PDFP (4-quarter growth)", f"{v:.1f}% ({d:%b %y})",
                     "~2% trend", _band(v, t["pdfp_hawk"], t["pdfp_dove"]),
                     "PDFP… typically carries more signal than GDP")

    def nfci():
        v, d = _last(get("NFCI"))
        return Check("Financial", "Chicago Fed NFCI", f"{v:+.2f} ({d:%d %b})",
                     "0 = average; < 0 = loose", _band(v, t["nfci_hawk"], t["nfci_dove"]),
                     "Hard pressed to describe broad financial conditions as restrictive")

    def hy():
        v, d = _last(get("BAMLH0A0HYM2"))
        return Check("Financial", "High-yield OAS", f"{v:.2f} pp ({d:%d %b})",
                     "Near historical lows = easy", _band(v, t["hy_hawk"], t["hy_dove"]),
                     "Credit spreads… near the low ends of their historical ranges")

    def sloos():
        v, d = _last(get("DRTSCILM"))
        return Check("Financial", "SLOOS: net % tightening C&I", f"{v:+.1f} ({d:%b %y})",
                     "< 0 = easing", _band(v, t["sloos_hawk"], t["sloos_dove"]),
                     "Standards… are on the easier end of their historical range")

    def claims():
        v, d = _last(get("IC4WSA"))
        return Check("Labor", "Initial claims (4-wk avg)", f"{v/1e3:,.0f}k ({d:%d %b})",
                     "Low = tight labor market", _band(v, t["claims_hawk"], t["claims_dove"]),
                     "Near their lowest level in decades")

    def theta():
        v = get("JTSJOL") / get("UNEMPLOY")
        x, d = _last(v)
        return Check("Labor", "Tightness θ = vacancies / unemployed", f"{x:.2f} ({d:%b %y})",
                     "≈ 1 = full employment", _band(x, t["theta_hawk"], t["theta_dove"]),
                     "People who want to work… are holding or finding jobs")

    def money():
        v, d = _last(indicators.yoy(get("M2SL"), 12))
        return Check("Money", "M2 (y/y)", f"{v:.1f}% ({d:%b %y})",
                     "≈ 4% (nominal GDP at 2% inflation)", _band(v, t["m2_hawk"], t["m2_dove"]),
                     "Money matters. It's not fashionable these days")

    for fn in (underlying, core6m, breadth, expectations, commodities, pdfp,
               nfci, hy, sloos, claims, theta, money):
        add(fn)
    return checks


def checklist_frame(checks: list[Check]) -> pd.DataFrame:
    label = {1: "🔴 hawkish", 0: "⚪ neutral", -1: "🔵 dovish"}
    return pd.DataFrame([{
        "Area": c.area, "Indicator": c.indicator, "Reading": c.reading,
        "Benchmark": c.benchmark, "Signal": label[c.signal], "Warsh": f"“{c.quote}”",
        "_signal": c.signal,
    } for c in checks])
