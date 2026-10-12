"""Fed-speak tone: a transparent hawk/dove lexicon + extractive summary.

This is the no-API-key fallback (the Claude classifier in
``src.ingest.llm`` replaces it when ANTHROPIC_API_KEY is set). It works at the
sentence level: only sentences about monetary policy count, each phrase hit
adds to the hawkish or dovish tally, and the score is the net share
scaled to −2 (very dovish) … +2 (very hawkish).

Lexicon scoring is crude — negations, conditionals ("if inflation rises we
would…") and irony slip through. Treat it as a first read and open the speech.
"""
from __future__ import annotations

import re

POLICY_TERMS = re.compile(
    r"\b(inflation|price stability|policy rate|federal funds|interest rates?|monetary policy|"
    r"labor market|employment|unemployment|rate cuts?|rate hikes?|restrictive|accommodat\w*|"
    r"neutral rate|r\*|tighten\w*|eas(e|ing)|dual mandate|FOMC)\b", re.I)

HAWKISH = [
    r"inflation (remains|is still|has been|is running) (too )?(high|elevated|above|stubborn|sticky)",
    r"upside risks? to inflation", r"inflation risks? (are|remain) (tilted )?to the upside",
    r"(remain|stay|keep|kept) (policy )?(modestly |sufficiently )?restrictive",
    r"further (policy )?(tightening|firming)", r"rais(e|ing) (the policy rate|interest rates|rates)",
    r"rate (hike|increase)s?", r"\b(why |a )?hike\b", r"not (yet )?(confident|convinced)",
    r"premature to (cut|ease|lower)", r"(persistent|sticky|stubborn) inflation",
    r"(un)?anchor\w* inflation expectations|expectations (could|may) (become )?unanchor",
    r"more work to do", r"work (is not|isn't) done", r"(hold|maintain) (rates|the policy rate) (steady|higher|for longer)",
    r"higher for longer", r"vigilan\w*", r"overheat\w*", r"(strong|robust|resilient) (demand|economy|labor market|growth)",
    r"financial conditions (are|remain) (loose|easy|accommodative)", r"not (very |particularly )?restrictive",
    r"risks? to inflation (outweigh|exceed|dominate|are greater)", r"focus\w* (is|has been|on) .{0,30}price stability",
    r"(raised|raise|raising|increased) the (federal funds|policy) rate", r"(adjust|tighten|firm)\w* (our|the) (policy )?stance",
    r"inflation .{0,40}(above|over) (our |the )?(2 percent )?(target|objective)", r"(elevated|high|higher) (levels of )?inflation",
    r"(could|may|might) prove (more )?(stubborn|persistent)", r"(firming|strong|robust|solid) (demand|spending|footing)",
    r"(labor market|economy) (remains?|continues?) (on solid footing|solid|strong|tight|healthy|resilient)",
    r"(historic|record|multi-decade) lows?", r"(haven't|have not|hasn't|has not) (seen|made) (much )?(progress|change) on (the )?inflation",
]
DOVISH = [
    r"(cut|cutting|lower|lowering|reduc\w*) (the policy rate|interest rates|rates)",
    r"rate (cut|reduction)s?", r"(further|policy|monetary) easing", r"less restrictive",
    r"recalibrat\w*", r"downside risks? to (employment|the labor market|growth|activity|the economy)",
    r"labor market (is )?(weaken\w*|cool\w*|soften\w*|deteriorat\w*)",
    r"unemployment (rate )?(has )?(risen|rising|increas\w*|moved up)",
    r"inflation (has )?(come down|moderat\w*|eas\w*|declin\w*|is moving down|fall\w*)",
    r"(good|substantial|continued|considerable) progress (on|toward) (inflation|our 2 percent)",
    r"(too|overly|unnecessarily) restrictive", r"risks? (are|have become) (more )?(balanced|two-sided)",
    r"(weak|weaker|slowing|soft) (demand|growth|hiring|job gains)", r"layoffs? (are )?(rising|increas\w*)",
    r"room to (cut|ease|lower)", r"toward (a more )?neutral",
    r"risks? to (maximum )?employment (outweigh|have (increased|risen|grown)|are (rising|greater))",
    r"(lowered|lowering|reduced|cut) the (federal funds|policy) rate", r"(slack|softening|cooling|weakness) in the labor market",
    r"inflation .{0,40}(near|close to|at|back to|approaching) (our |the )?(2 percent )?(target|objective)",
    r"inflation (should|will|is likely to|is expected to) (continue to )?(come|move|fall|decline|ease)",
    r"(policy|rates?) (is|are) (well |sufficiently |clearly )?restrictive",
]
_H = [re.compile(p, re.I) for p in HAWKISH]
_D = [re.compile(p, re.I) for p in DOVISH]

LABELS = [(-1.25, "Dovish"), (-0.4, "Lean dovish"), (0.4, "Neutral"), (1.25, "Lean hawkish")]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", text) if 40 <= len(s.strip()) <= 600]


def label_for(score: float | None, about_policy: bool = True) -> str:
    if not about_policy or score is None:
        return "Not about policy"
    for cut, name in LABELS:
        if score <= cut:
            return name
    return "Hawkish"


def score_text(text: str, min_policy_sentences: int = 4) -> dict:
    """Lexicon tone of a speech: score in [−2, 2], hit counts and top sentences."""
    sents = split_sentences(text)
    policy = [s for s in sents if POLICY_TERMS.search(s)]
    h_tot = d_tot = 0
    ranked = []
    for i, s in enumerate(policy):
        h = sum(1 for p in _H if p.search(s))
        d = sum(1 for p in _D if p.search(s))
        h_tot, d_tot = h_tot + h, d_tot + d
        ranked.append((h + d, len(POLICY_TERMS.findall(s)), i, s))
    about_policy = len(policy) >= min_policy_sentences
    # +4 shrinks small samples toward neutral: 2 hits alone can't reach a strong label
    score = 2 * (h_tot - d_tot) / (h_tot + d_tot + 4) if about_policy else None
    top = sorted(ranked, key=lambda r: (-r[0], -r[1]))[:3]
    summary = " … ".join(s for *_, s in sorted(top, key=lambda r: r[2]))
    return {"tone_score": score, "tone_label": label_for(score, about_policy),
            "hawk_hits": h_tot, "dove_hits": d_tot, "policy_sentences": len(policy),
            "about_policy": about_policy, "summary": summary, "tone_method": "lexicon"}
