"""Fed-speak sources: speeches by FOMC participants, the Board calendar and
FOMC meeting dates.

Coverage (verified 2026-10):
  Board of Governors   JSON federalreserve.gov/json/ne-speeches.json (full list)
  BIS                  RSS  central bankers' speeches (catches NY Fed, others)
  New York, Boston, Philadelphia, Cleveland, Chicago, Minneapolis, Dallas,
  San Francisco        HTML list pages (president-specific links)
  Richmond             RSS
  Atlanta              JSON feed API behind the speeches page
  St. Louis, Kansas City   NOT reachable by scripted clients (Akamai bot
                       protection drops the connection) — covered only via
                       BIS, the optional Claude web search, or manual entries.

Every source is independent: a broken site logs a warning and the rest go on.
Site layouts change — when a source returns nothing, check its pattern here.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30
MAX_PER_SOURCE = 10   # newest links followed per regional list page

MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
          "November|December")
_DATE_RE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),\s+(20\d\d)\b")


@dataclass
class SpeechRef:
    speaker: str                 # roster key
    url: str
    title: str
    date: pd.Timestamp | None    # None = resolve from the speech page
    source: str


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(_get(url).text, "lxml")


def _links(url: str, href_pattern: str, base: str | None = None) -> list[tuple[str, str]]:
    """(absolute url, link text) for anchors whose href matches, de-duplicated."""
    soup = _soup(url)
    seen, out = set(), []
    rx = re.compile(href_pattern)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not rx.search(href):
            continue
        absu = urljoin(base or url, href).split("#")[0]
        text = " ".join(a.get_text(" ").split())
        if absu in seen or len(text) < 8:
            continue
        seen.add(absu)
        out.append((absu, text))
    return out


def _yymmdd(s: str) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(f"20{s[:2]}-{s[2:4]}-{s[4:6]}")
    except ValueError:
        return None


def _rss_items(resp: requests.Response) -> list[dict]:
    # decode with utf-8-sig: the Board feed starts with a BOM that breaks the XML parser
    soup = BeautifulSoup(resp.content.decode("utf-8-sig"), "xml")
    items = []
    for it in soup.find_all("item"):
        get = lambda tag: (it.find(tag).get_text(strip=True) if it.find(tag) else "")  # noqa: E731
        items.append({"title": get("title"), "link": get("link") or it.get("rdf:about", ""),
                      "date": get("pubDate") or get("dc:date") or get("date"),
                      "description": get("description"), "creator": get("dc:creator") or get("creator")})
    return items


def _parse_date(s: str) -> pd.Timestamp | None:
    if not s:
        return None
    try:
        return pd.Timestamp(parsedate_to_datetime(s)).tz_localize(None).normalize()
    except (TypeError, ValueError):
        pass
    ts = pd.to_datetime(s, errors="coerce", utc=True)
    return None if pd.isna(ts) else ts.tz_localize(None).normalize()


# --- Sources ---------------------------------------------------------------
def board(roster: pd.DataFrame) -> list[SpeechRef]:
    """Full Board speech list (the RSS only carries the latest 15)."""
    raw = _get("https://www.federalreserve.gov/json/ne-speeches.json").content.decode("utf-8-sig")
    board_names = roster.loc[roster["seat"] == "board", ["name", "key"]].values
    out = []
    for it in json.loads(raw):
        key = next((k for n, k in board_names if re.search(rf"\b{n}\b", it.get("s", ""))), None)
        date = pd.to_datetime(it.get("d", ""), errors="coerce")
        if key and not pd.isna(date):
            out.append(SpeechRef(key, urljoin("https://www.federalreserve.gov", it["l"]),
                                 html.unescape(it.get("t", "")), date.normalize(), "Board"))
    return sorted(out, key=lambda r: r.date, reverse=True)[:60]


def bis(roster: pd.DataFrame) -> list[SpeechRef]:
    """BIS aggregator — kept for Reserve Bank presidents only (Board has its own feed)."""
    pres = roster[roster["seat"] != "board"]
    out = []
    for it in _rss_items(_get("https://www.bis.org/doclist/cbspeeches.rss")):
        if "Federal Reserve" not in it["description"]:
            continue
        for name, key in zip(pres["name"], pres["key"]):
            if re.search(rf"\b{name}\b", it["creator"] + " " + it["description"]):
                out.append(SpeechRef(key, it["link"], it["title"], _parse_date(it["date"]), "BIS"))
                break
    return out


def new_york(_) -> list[SpeechRef]:
    out = []
    for url, text in _links("https://www.newyorkfed.org/newsevents/speeches",
                            r"/newsevents/speeches/20\d\d/wil\d{6}"):
        m = re.search(r"wil(\d{6})", url)
        out.append(SpeechRef("williams", url, text.removeprefix("Williams:").strip(),
                             _yymmdd(m.group(1)), "NY Fed"))
    return out[:MAX_PER_SOURCE]


def boston(_) -> list[SpeechRef]:
    return [SpeechRef("collins", u, t, None, "Boston Fed") for u, t in
            _links("https://www.bostonfed.org/news-and-events/speeches.aspx",
                   r"/news-and-events/speeches/20\d\d/[^/]+\.aspx")][:MAX_PER_SOURCE]


def philadelphia(_) -> list[SpeechRef]:
    out = []
    for u, t in _links("https://www.philadelphiafed.org/the-economy/speeches-anna-paulson",
                       r"^/the-economy/[a-z-]+/(\d{6}-|monetary-policy-perspective)"):
        m = re.search(r"/(\d{6})-", u)
        out.append(SpeechRef("paulson", u, t, _yymmdd(m.group(1)) if m else None, "Philadelphia Fed"))
    return out[:MAX_PER_SOURCE]


def cleveland(_) -> list[SpeechRef]:
    """The list is client-rendered from JSON embedded in the page: read slugs from it."""
    raw = html.unescape(_get("https://www.clevelandfed.org/collections/speeches").text)
    out, seen = [], set()
    for m in re.finditer(r"/collections/speeches/(?:20\d\d/)?sp-(\d{8})-([a-z0-9-]+)", raw):
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        url = f"https://www.clevelandfed.org/collections/speeches/{m.group(1)[:4]}/sp-{m.group(1)}-{m.group(2)}"
        out.append(SpeechRef("hammack", url, m.group(2).replace("-", " ").capitalize(),
                             pd.Timestamp(m.group(1)), "Cleveland Fed"))
    return sorted(out, key=lambda r: r.date, reverse=True)[:MAX_PER_SOURCE]


def richmond(_) -> list[SpeechRef]:
    items = _rss_items(_get("https://www.richmondfed.org/press_room/speeches?cc_view=rss"))
    return [SpeechRef("barkin", urljoin("https://www.richmondfed.org", it["link"]), it["title"],
                      _parse_date(it["date"]), "Richmond Fed") for it in items[:MAX_PER_SOURCE]]


def atlanta(roster: pd.DataFrame) -> list[SpeechRef]:
    """Atlanta's speech list is rendered from a JSON feed; keep the current president."""
    name = roster.loc[roster["seat"] == "atlanta", "name"].iloc[0]
    page = _get("https://www.atlantafed.org/news/speeches").text
    form = page[page.find('id="filter_feed_'):]
    form = form[:form.find("</form>")]
    params = {}
    for inp in re.findall(r'<input[^>]*type="hidden"[^>]*>', form):
        n, v = re.search(r'name="([^"]+)"', inp), re.search(r'value="([^"]*)"', inp)
        if n and v and v.group(1):
            params[n.group(1)] = v.group(1)
    params["PageSize"] = "20"
    data = _get("https://www.atlantafed.org/api/feed/getFilteredResults", params=params).json()
    out = []
    for it in json.loads(data["FilteredFeedItemsJson"]):
        if any(name.lower() in a.get("FullName", "").lower() for a in it.get("Authors", [])):
            out.append(SpeechRef("venable", urljoin("https://www.atlantafed.org", it["Url"]),
                                 BeautifulSoup(it["Title"], "lxml").get_text(),
                                 pd.Timestamp(it["Date"]).normalize(), "Atlanta Fed"))
    return out


def chicago(_) -> list[SpeechRef]:
    """Chicago event pages carry no machine-readable date; read it from the slug
    (``/publications/speeches/2026/sept-30-norc``)."""
    out = []
    for u, t in _links(
            "https://www.chicagofed.org/utilities/about-us/office-of-the-president/office-of-the-president-speaking",
            r"/publications/speeches/20\d\d/"):
        m = re.search(r"/(20\d\d)/([a-z]{3})[a-z]*-(\d{1,2})-", u)
        date = pd.to_datetime(f"{m.group(2)} {m.group(3)} {m.group(1)}", errors="coerce") if m else None
        out.append(SpeechRef("goolsbee", u, t, None if date is None or pd.isna(date) else date,
                             "Chicago Fed"))
    return out[:MAX_PER_SOURCE]


def minneapolis(_) -> list[SpeechRef]:
    return [SpeechRef("kashkari", u, t, None, "Minneapolis Fed") for u, t in _links(
        "https://www.minneapolisfed.org/people/neel-kashkari", r"^/(speeches|article)/20\d\d/")
        ][:MAX_PER_SOURCE]


def dallas(_) -> list[SpeechRef]:
    out = []
    for u, t in _links("https://www.dallasfed.org/news/speeches/logan",
                       r"/news/speeches/logan/20\d\d/lkl\d{6}"):
        m = re.search(r"lkl(\d{6})", u)
        out.append(SpeechRef("logan", u, t, _yymmdd(m.group(1)), "Dallas Fed"))
    return out[:MAX_PER_SOURCE]


def san_francisco(_) -> list[SpeechRef]:
    return [SpeechRef("daly", u, t, None, "SF Fed") for u, t in _links(
        "https://www.frbsf.org/news-and-media/speeches/mary-c-daly/",
        r"/speeches/mary-c-daly/20\d\d/\d\d/[^/]+")][:MAX_PER_SOURCE]


SOURCES: dict[str, Callable[[pd.DataFrame], list[SpeechRef]]] = {
    "Board": board, "BIS": bis, "New York": new_york, "Boston": boston,
    "Philadelphia": philadelphia, "Cleveland": cleveland, "Richmond": richmond,
    "Atlanta": atlanta, "Chicago": chicago, "Minneapolis": minneapolis,
    "Dallas": dallas, "San Francisco": san_francisco,
}
UNREACHABLE = {"St. Louis": "musalem", "Kansas City": "schmid"}


def speech_index(roster: pd.DataFrame) -> tuple[list[SpeechRef], dict[str, str]]:
    """Collect references from every source; returns (refs, {source: error})."""
    refs, errors = [], {}
    for name, fn in SOURCES.items():
        try:
            refs.extend(fn(roster))
        except Exception as exc:  # noqa: BLE001 — one broken site must not stop the rest
            errors[name] = str(exc)[:200]
    return refs, errors


# --- Speech documents ------------------------------------------------------
_META_DATE = ["article:published_time", "date", "dc.date", "DC.date.issued", "citation_date",
              "og:published_time", "publish-date", "pubdate"]


def fetch_document(url: str) -> tuple[str, pd.Timestamp | None]:
    """Main text of a speech page and its date (meta tags, then the text)."""
    soup = _soup(url)
    date = None
    for key in _META_DATE:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            date = _parse_date(tag["content"])
            if date is not None:
                break
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        t.decompose()
    root = (soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"})
            or soup.find(id=re.compile("content", re.I)) or soup.body or soup)
    paras = [" ".join(p.get_text(" ").split()) for p in root.find_all(["p", "li", "h2", "h3"])]
    text = "\n".join(p for p in paras if len(p) > 1)
    if date is None:
        m = _DATE_RE.search(" ".join(root.get_text(" ").split())[:4000])
        if m:
            date = pd.Timestamp(f"{m.group(1)} {m.group(2)} {m.group(3)}")
    return text, date


# --- Calendar & meetings ---------------------------------------------------
def board_calendar(roster: pd.DataFrame) -> pd.DataFrame:
    """Board calendar events (speeches, testimony, FOMC, Beige Book) as rows."""
    raw = _get("https://www.federalreserve.gov/json/calendar.json")
    data = json.loads(raw.content.decode("utf-8-sig"))
    rows = []
    for e in data["events"][:-1]:     # the feed ends with a sentinel element
        if e.get("type") not in ("Speeches", "Testimony", "FOMC", "Beige"):
            continue
        speaker = next((k for n, k in zip(roster["name"], roster["key"])
                        if re.search(rf"\b{n}\b", e.get("title", ""))), None)
        for day in str(e.get("days", "")).split(","):
            try:
                date = pd.Timestamp(f"{e['month']}-{int(day):02d}")
            except (ValueError, KeyError):
                continue
            rows.append({
                "date": date, "time_et": e.get("time", ""), "speaker": speaker,
                "event": BeautifulSoup(e.get("title", ""), "lxml").get_text(),
                "topic": BeautifulSoup(BeautifulSoup(e.get("description", "") or "", "lxml")
                                       .get_text(), "lxml").get_text(),
                "location": BeautifulSoup(e.get("location", "") or "", "lxml").get_text(),
                "type": e["type"], "link": e.get("live") or e.get("link") or "",
                "source": "Board calendar",
            })
    return pd.DataFrame(rows)


def fomc_meetings() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Scheduled FOMC meetings (start, end) from the Board's meeting calendar."""
    soup = _soup("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    meetings = []
    for panel in soup.find_all(class_=re.compile(r"\bpanel\b")):
        head = panel.find(class_=re.compile("panel-heading"))
        m = re.search(r"(20\d\d) FOMC Meetings", head.get_text() if head else "")
        if not m:
            continue
        year = int(m.group(1))
        for row in panel.find_all(class_=re.compile(r"fomc-meeting\b|row fomc-meeting")):
            mon = row.find(class_=re.compile("fomc-meeting__month"))
            day = row.find(class_=re.compile("fomc-meeting__date"))
            if not mon or not day:
                continue
            months = re.findall(r"[A-Za-z]+", mon.get_text())
            days = re.findall(r"\d+", day.get_text())
            if not months or not days or "unscheduled" in day.get_text().lower():
                continue
            m0, m1 = months[0][:3], months[-1][:3]
            start = pd.Timestamp(f"{m0} {days[0]} {year}")
            end = pd.Timestamp(f"{m1} {days[-1]} {year}")
            meetings.append((start, end))
    return sorted(set(meetings))
