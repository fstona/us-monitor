"""BLS API v2 — CPI and PPI series (PCE nowcast inputs).

Works without a key (25 series / query, 10 years, 25 queries / day); with
``BLS_API_KEY`` in .env: 50 series / query, 20 years, 500 queries / day.

Never type a series ID from memory: check it against the official catalogs
(``catalog("cu")`` for CPI, ``catalog("pc")`` for PPI by industry). PPI
industry series are NOT seasonally adjusted (no SA versions exist).
"""
from __future__ import annotations

import io
import os
import time

import pandas as pd
import requests

URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CATALOG_URL = "https://download.bls.gov/pub/time.series/{survey}/{survey}.series"


def _key() -> str | None:
    return os.getenv("BLS_API_KEY") or None


def fetch(series_ids: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    """Monthly observations, long format: series_id, date, value."""
    key = _key()
    per_query, max_years = (50, 20) if key else (25, 10)
    rows = []
    ids = list(dict.fromkeys(series_ids))
    for y0 in range(start_year, end_year + 1, max_years):
        y1 = min(y0 + max_years - 1, end_year)
        for i in range(0, len(ids), per_query):
            payload = {"seriesid": ids[i:i + per_query], "startyear": str(y0), "endyear": str(y1)}
            if key:
                payload["registrationkey"] = key
            r = requests.post(URL, json=payload, timeout=90)
            r.raise_for_status()
            j = r.json()
            if j.get("status") != "REQUEST_SUCCEEDED":
                raise RuntimeError(f"BLS: {j.get('status')} — {j.get('message')}")
            for s in j["Results"]["series"]:
                for d in s["data"]:
                    if not d["period"].startswith("M") or d["period"] == "M13":
                        continue
                    rows.append({"series_id": s["seriesID"],
                                 "date": pd.Timestamp(f"{d['year']}-{d['period'][1:]}-01"),
                                 "value": pd.to_numeric(d["value"], errors="coerce")})
            time.sleep(0.5)
    df = pd.DataFrame(rows, columns=["series_id", "date", "value"])
    missing = set(ids) - set(df["series_id"])
    if missing:
        raise KeyError(f"BLS returned no data for: {sorted(missing)}")
    return df.dropna().sort_values(["series_id", "date"]).reset_index(drop=True)


def catalog(survey: str) -> pd.DataFrame:
    """Official series list ('cu' = CPI, 'pc' = PPI industry) — for verifying IDs
    while building the concordance (development only; the nowcast refresh uses
    the API and does not need this).

    download.bls.gov rejects requests (403) unless the User-Agent carries a
    contact e-mail: set BLS_CONTACT_EMAIL in .env.
    """
    contact = os.getenv("BLS_CONTACT_EMAIL")
    if not contact:
        raise RuntimeError("Set BLS_CONTACT_EMAIL in .env (BLS requires a contact for downloads).")
    ua = f"us-monitor ({contact})"
    r = requests.get(CATALOG_URL.format(survey=survey), headers={"User-Agent": ua}, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df.apply(lambda c: c.str.strip())
