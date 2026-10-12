"""FRED API access (raw fetch only — routing/caching live in ``src.data``).

The ingestion job calls ``fetch_live`` / ``fetch_info`` directly to force the API.
"""
from __future__ import annotations

import pandas as pd
from fredapi import Fred

from src import config

_client: Fred | None = None


def _fred() -> Fred:
    global _client
    if _client is None:
        if not config.FRED_API_KEY:
            raise RuntimeError(
                "FRED_API_KEY is not set. Copy us-monitor/.env.example to "
                "us-monitor/.env and paste your key (needed to refresh data)."
            )
        _client = Fred(api_key=config.FRED_API_KEY)
    return _client


def fetch_live(series_id: str) -> pd.Series:
    """Fetch a series straight from the FRED API (no mode logic, no cache)."""
    series = _fred().get_series(series_id)
    series.index = pd.to_datetime(series.index)
    return series.dropna()


def fetch_info(series_id: str) -> dict:
    """Series metadata from FRED, incl. ``last_updated`` (release timestamp)."""
    return _fred().get_series_info(series_id).to_dict()
