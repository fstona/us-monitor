"""Optional Claude layer for Fed-speak (enabled when ANTHROPIC_API_KEY is set).

Three calls, all returning schema-validated JSON (structured outputs):
  classify()        summary + hawk/dove tone of one speech transcript
  search_remarks()  web search for recent remarks by participants whose banks
                    can't be scraped (St. Louis, Kansas City) and interviews
  search_calendar() web search for scheduled Fed speakers in the next days

Model: Claude Opus 5.5 with server-side refusal fallbacks enabled
(``fallbacks="default"``) so a rare safety decline is retried on another model
instead of dropping the speech. Cost is small: one classification is a single
~5–15k-token request, and results are cached per speech URL by the job.
"""
from __future__ import annotations

import json
import os

import pandas as pd

from src import config  # noqa: F401 — importing config loads us-monitor/.env into os.environ

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_CONTINUATIONS = 5

TONE_LABELS = ["Dovish", "Lean dovish", "Neutral", "Lean hawkish", "Hawkish", "Not about policy"]

TONE_GUIDE = (
    "Tone scale for U.S. monetary policy: -2 = clearly dovish (argues for cutting rates or "
    "against further tightening; emphasizes labor-market weakness or downside risks), "
    "0 = balanced, +2 = clearly hawkish (argues for raising rates or holding them higher for "
    "longer; emphasizes inflation above target or upside inflation risks). Judge the speaker's "
    "own policy view, not the data they recite. If the remarks are not about monetary policy "
    "(e.g. bank supervision, payments, community development), set about_monetary_policy to "
    "false and tone_score to 0."
)

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "about_monetary_policy": {"type": "boolean"},
        "tone_score": {"type": "number"},
        "tone_label": {"type": "string", "enum": TONE_LABELS},
        "rate_view": {"type": "string", "enum": ["hike", "hold", "cut", "unclear"]},
        "summary": {"type": "string"},
        "key_quote": {"type": "string"},
    },
    "required": ["about_monetary_policy", "tone_score", "tone_label", "rate_view",
                 "summary", "key_quote"],
    "additionalProperties": False,
}

_REMARKS_SCHEMA = {
    "type": "object",
    "properties": {"remarks": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "speaker_key": {"type": "string"}, "date": {"type": "string"},
            "title": {"type": "string"}, "url": {"type": "string"},
            "summary": {"type": "string"}, "tone_score": {"type": "number"},
            "tone_label": {"type": "string", "enum": TONE_LABELS},
            "rate_view": {"type": "string", "enum": ["hike", "hold", "cut", "unclear"]},
        },
        "required": ["speaker_key", "date", "title", "url", "summary", "tone_score",
                     "tone_label", "rate_view"],
        "additionalProperties": False,
    }}},
    "required": ["remarks"],
    "additionalProperties": False,
}

_CALENDAR_SCHEMA = {
    "type": "object",
    "properties": {"events": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "date": {"type": "string"}, "time_et": {"type": "string"},
            "speaker_key": {"type": "string"}, "event": {"type": "string"},
            "topic": {"type": "string"}, "link": {"type": "string"},
        },
        "required": ["date", "time_et", "speaker_key", "event", "topic", "link"],
        "additionalProperties": False,
    }}},
    "required": ["events"],
    "additionalProperties": False,
}


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _client():
    import anthropic
    return anthropic.Anthropic()


def _json_call(prompt: str, schema: dict, effort: str, web_search: bool = False) -> dict:
    """One structured-output request; resumes server-tool ``pause_turn`` stops."""
    client = _client()
    messages = [{"role": "user", "content": prompt}]
    tools = ([{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}]
             if web_search else [])
    for _ in range(MAX_CONTINUATIONS):
        kwargs = dict(
            model=MODEL, max_tokens=16000, messages=messages,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA], fallbacks="default",
        )
        if tools:
            kwargs["tools"] = tools
        response = client.beta.messages.create(**kwargs)
        if response.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": response.content}]
            continue
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined: {getattr(response.stop_details, 'category', None)}")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude response hit max_tokens")
        texts = [b.text for b in response.content if b.type == "text"]
        if not texts:
            raise RuntimeError("Claude returned no text block")
        return json.loads(texts[-1])
    raise RuntimeError("Too many pause_turn continuations")


def classify(speaker: str, role: str, title: str, date: str, text: str) -> dict:
    """Summary + tone of one transcript (full text — never truncated)."""
    prompt = (
        f"You are a Fed watcher. Classify the monetary-policy tone of these remarks by "
        f"{speaker} ({role}), titled \"{title}\", delivered {date}.\n\n{TONE_GUIDE}\n\n"
        "summary: 2-3 sentences on the speaker's view of the economy and of policy. "
        "key_quote: the single most policy-relevant sentence, verbatim (empty if none).\n\n"
        f"<transcript>\n{text}\n</transcript>"
    )
    out = _json_call(prompt, _CLASSIFY_SCHEMA, effort="low")
    out["tone_score"] = max(-2.0, min(2.0, float(out["tone_score"])))
    out["tone_method"] = "claude"
    return out


def search_remarks(people: pd.DataFrame, since: pd.Timestamp) -> pd.DataFrame:
    """Recent public remarks (speeches, interviews, Q&As) found by web search."""
    who = "; ".join(f"{r.key} = {r.full_name} ({r.position}, {r.institution})"
                    for r in people.itertuples())
    prompt = (
        f"Today is {pd.Timestamp.today():%Y-%m-%d}. Find public remarks on the economy or monetary "
        f"policy made since {since:%Y-%m-%d} by these FOMC participants: {who}. Include speeches, "
        "media interviews and Q&As, using primary sources or major news outlets (Reuters, "
        "Bloomberg, WSJ, CNBC, AP). One entry per distinct appearance, with its date "
        "(YYYY-MM-DD) and URL. Use speaker_key exactly as given. Return an empty list if you find "
        f"nothing — do not guess.\n\n{TONE_GUIDE}"
    )
    rows = _json_call(prompt, _REMARKS_SCHEMA, effort="medium", web_search=True)["remarks"]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["about_policy"] = df["tone_label"] != "Not about policy"
    df["tone_method"] = "claude+web"
    df["source"] = "Web search"
    return df.rename(columns={"speaker_key": "speaker"}).dropna(subset=["date"])


def search_calendar(roster: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    """Scheduled appearances by FOMC participants over the next ``days`` days."""
    today = pd.Timestamp.today().normalize()
    keys = ", ".join(f"{r.key} ({r.full_name}, {r.institution})" for r in roster.itertuples())
    prompt = (
        f"Today is {today:%Y-%m-%d}. List public speaking engagements scheduled from "
        f"{today:%Y-%m-%d} through {today + pd.Timedelta(days=days):%Y-%m-%d} for FOMC "
        f"participants: {keys}. Check the regional Reserve Banks' event pages and financial "
        "calendars. Times in US Eastern (empty if unknown). Use speaker_key exactly as given. "
        "Only include events you can source with a link — do not guess."
    )
    df = pd.DataFrame(_json_call(prompt, _CALENDAR_SCHEMA, effort="medium", web_search=True)["events"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["source"] = "Web search"
    df["type"] = "Speeches"
    return df.rename(columns={"speaker_key": "speaker"}).dropna(subset=["date"])

