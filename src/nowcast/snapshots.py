"""Raw input vintages: every download is kept with its capture time.

data/nowcast/snapshots/<source>_<YYYYMMDDTHHMMZ>.parquet — the start of a true
real-time track record (spec §5). Lives under data/ (not versioned).
"""
from __future__ import annotations

import pandas as pd

from src import config

DIR = config.DATA_DIR / "nowcast" / "snapshots"


def save(source: str, df: pd.DataFrame) -> str:
    DIR.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%MZ")
    path = DIR / f"{source}_{stamp}.parquet"
    df.to_parquet(path, index=False)
    return path.name


def latest(source: str) -> pd.DataFrame | None:
    files = sorted(DIR.glob(f"{source}_*.parquet"))
    return pd.read_parquet(files[-1]) if files else None
