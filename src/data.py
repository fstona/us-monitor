"""Single entry point for every series: read from the store, refresh from the source.

Reading never touches the network (``get_series`` reads ``src.store``).
``refresh`` downloads from FRED/BEA and writes the store; a series whose
download fails keeps its previous data. Refresh needs the API keys in .env —
without them (e.g. a read-only deployment) the dashboard just reads.
"""
from __future__ import annotations

import time

import pandas as pd

from src import config, store
from src.ingest import bea, fred

FRED_PAUSE_S = 0.25  # stay under FRED's 120 requests/minute


def get_series(series_id: str) -> pd.Series:
    return store.get_series(series_id)


def can_refresh() -> bool:
    return bool(config.FRED_API_KEY)


def release_info() -> pd.DataFrame:
    """Per series: ``last_updated`` (source release stamp) and ``fetched_at``."""
    return store.get_metadata()


def fetched_at(series_id: str) -> pd.Timestamp | None:
    ts = store.get_metadata()["fetched_at"].get(series_id)
    return None if ts is None or pd.isna(ts) else ts


def refresh(series_ids: list[str], progress=None) -> list[str]:
    """Download these series from their sources into the store.

    Returns the IDs that failed (their stored data is left as it was).
    ``progress(i, n, id)`` is an optional callback for a progress bar.
    """
    now = pd.Timestamp.now(tz="UTC")
    series, meta, failures = {}, [], []
    diffusion = None
    for i, sid in enumerate(series_ids):
        if progress:
            progress(i, len(series_ids), sid)
        spec = config.SERIES_BY_ID.get(sid)
        try:
            if spec is not None and spec.source == "bea":
                if diffusion is None:          # one BEA call fills both diffusion series
                    diffusion = bea.fetch_diffusion()
                series[sid] = diffusion[bea.DIFFUSION_IDS[sid]].dropna()
                released = now
            else:
                series[sid] = fred.fetch_live(sid)
                released = pd.to_datetime(fred.fetch_info(sid).get("last_updated"),
                                          utc=True, errors="coerce")
                time.sleep(FRED_PAUSE_S)
            meta.append({"series_id": sid, "last_updated": released, "fetched_at": now})
        except Exception as exc:  # noqa: BLE001 — keep going; old data stays in the store
            print(f"[warn] refresh {sid}: {exc}")
            failures.append(sid)
    if series:
        store.save_series(series, pd.DataFrame(meta))
    return failures
