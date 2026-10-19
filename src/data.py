"""Single entry point for every series: read from the store, refresh from the source.

Reading never touches the network (``get_series`` reads ``src.store``).
``refresh`` downloads from FRED/BEA and writes the store; a series whose
download fails keeps its previous data. Refresh needs the API keys in .env —
without them (e.g. a read-only deployment) the dashboard just reads.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

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


@dataclass
class RefreshResult:
    updated: list = field(default_factory=list)     # new data downloaded
    unchanged: list = field(default_factory=list)   # source had nothing new: not downloaded
    failed: list = field(default_factory=list)      # error: previous data kept

    def summary(self) -> str:
        n = len(self.updated) + len(self.unchanged) + len(self.failed)
        msg = f"{len(self.updated)} of {n} series had new data ({len(self.unchanged)} unchanged, not re-downloaded)"
        return msg + (f"; failed, previous data kept: {', '.join(self.failed)}" if self.failed else "")


def refresh(series_ids: list[str], progress=None) -> RefreshResult:
    """Bring these series up to date in the store, downloading only what changed.

    FRED: one light call reads the series' last-updated stamp; the observations are
    downloaded only if it differs from the stored one. BEA diffusion: recomputed only
    when a new PCE month exists, from the last 3 years merged into the stored history.
    A failed download leaves the stored series untouched.
    ``progress(i, n, id)`` is an optional callback for a progress bar.
    """
    ids = list(dict.fromkeys(series_ids))
    is_bea = lambda sid: getattr(config.SERIES_BY_ID.get(sid), "source", "fred") == "bea"   # noqa: E731
    ordered = [s for s in ids if not is_bea(s)] + [s for s in ids if is_bea(s)]   # BEA after PCEPI
    now = pd.Timestamp.now(tz="UTC")
    old_meta = store.get_metadata()
    res, series, meta = RefreshResult(), {}, []
    for i, sid in enumerate(ordered):
        if progress:
            progress(i, len(ordered), sid)
        try:
            if is_bea(sid):
                new = _bea_diffusion(sid, series)
                released = now if new is not None else old_meta["last_updated"].get(sid)
            else:
                released = pd.to_datetime(fred.fetch_info(sid).get("last_updated"), utc=True, errors="coerce")
                time.sleep(FRED_PAUSE_S)
                old = old_meta["last_updated"].get(sid)
                same = store.has_series(sid) and old is not None and not pd.isna(old) and old == released
                new = None if same else fred.fetch_live(sid)
                if new is not None:
                    time.sleep(FRED_PAUSE_S)
            if new is None:
                res.unchanged.append(sid)
            else:
                series[sid] = new
                res.updated.append(sid)
            meta.append({"series_id": sid, "last_updated": released, "fetched_at": now})
        except Exception as exc:  # noqa: BLE001 — keep going; old data stays in the store
            print(f"[warn] refresh {sid}: {exc}")
            res.failed.append(sid)
    if meta:
        store.save_series(series, pd.DataFrame(meta))
    return res


def _bea_diffusion(sid: str, just_downloaded: dict) -> pd.Series | None:
    """New diffusion series, or None if no PCE month newer than what is stored."""
    pce = just_downloaded.get("PCEPI")
    last_pce = pce.index.max() if pce is not None else (
        store.get_series("PCEPI").index.max() if store.has_series("PCEPI") else None)
    if store.has_series(sid) and last_pce is not None and store.get_series(sid).index.max() >= last_pce:
        return None
    if store.has_series(sid):                       # incremental: recent years only
        fresh = bea.fetch_diffusion(years=bea.recent_years(3))[bea.DIFFUSION_IDS[sid]].dropna()
        hist = store.get_series(sid)
        return pd.concat([hist[hist.index < fresh.index.min()], fresh])
    return bea.fetch_diffusion()[bea.DIFFUSION_IDS[sid]].dropna()
