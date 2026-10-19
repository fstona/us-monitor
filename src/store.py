"""The local data store — the ONLY place the dashboard reads data from.

    STORE_PATH/observations.parquet   long format: series_id, date, value
    STORE_PATH/metadata.parquet       series_id, last_updated (source release), fetched_at
    STORE_PATH/<table>.parquet        other tables (Fed-speak)

Nothing refreshes on its own: data changes only when a refresh button (or
``python -m src.jobs.ingest``) calls ``data.refresh``, which writes here via
``save_series``. A failed download never touches what is already stored.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src import config

OBS = config.STORE_PATH / "observations.parquet"
META = config.STORE_PATH / "metadata.parquet"


@lru_cache(maxsize=1)
def _series_map() -> dict[str, pd.Series]:
    if not OBS.exists():
        return {}
    df = pd.read_parquet(OBS)
    df["date"] = pd.to_datetime(df["date"])
    return {sid: g.set_index("date")["value"].sort_index() for sid, g in df.groupby("series_id")}


def has_data() -> bool:
    return bool(_series_map())


def has_series(series_id: str) -> bool:
    return series_id in _series_map()


def get_series(series_id: str) -> pd.Series:
    try:
        return _series_map()[series_id]
    except KeyError:
        raise KeyError(f"{series_id} is not in the local store yet — use a refresh button.") from None


@lru_cache(maxsize=1)
def get_metadata() -> pd.DataFrame:
    """Indexed by series_id: ``last_updated`` and ``fetched_at`` (UTC)."""
    if not META.exists():
        return pd.DataFrame(columns=["last_updated", "fetched_at"])
    df = pd.read_parquet(META)
    for c in ("last_updated", "fetched_at"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce") if c in df else pd.NaT
    return df.set_index("series_id")[["last_updated", "fetched_at"]]


def save_series(series: dict[str, pd.Series], meta: pd.DataFrame) -> None:
    """Replace these series (and their metadata rows); keep everything else."""
    config.STORE_PATH.mkdir(parents=True, exist_ok=True)
    if series:
        new_obs = pd.concat([pd.DataFrame({"series_id": sid, "date": s.index, "value": s.values})
                             for sid, s in series.items()], ignore_index=True)
        if OBS.exists():
            old = pd.read_parquet(OBS)
            new_obs = pd.concat([old[~old["series_id"].isin(series)], new_obs], ignore_index=True)
        new_obs.to_parquet(OBS, index=False)

    if META.exists():
        old = pd.read_parquet(META)
        meta = pd.concat([old[~old["series_id"].isin(meta["series_id"])], meta], ignore_index=True)
    meta.to_parquet(META, index=False)
    _series_map.cache_clear()
    get_metadata.cache_clear()


def get_table(name: str) -> pd.DataFrame:
    """A non-series table written by a job (e.g. 'fedspeak_speeches')."""
    path = config.STORE_PATH / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No table {name!r} yet — use the refresh button.")
    return pd.read_parquet(path)
