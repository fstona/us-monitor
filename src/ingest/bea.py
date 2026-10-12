"""BEA API access — PCE price diffusion (Warsh, Jackson Hole 2026).

Warsh: "I find it instructive to disaggregate the 199 individual components of
the PCE" — 54% showed price increases above 3%, vs ~32% in the two decades
before the pandemic. We recompute that share from BEA NIPA Table 2.4.4U
(price indexes for PCE by type of product, monthly), by COUNT of components,
on both a 12-month and a 6-month annualized basis.

Caveat: the table mixes leaf components with aggregates; the count uses every
line. To match the speech's 199 leaf components exactly, pass their
``SeriesCode`` set to ``fetch_diffusion(include_codes=...)``.
"""
from __future__ import annotations

import pandas as pd
import requests

from src import config

BEA_URL = "https://apps.bea.gov/api/data/"
PRICE_TABLE = "U20404"

# Catalog IDs -> column of the diffusion frame.
DIFFUSION_IDS = {"BEA_PCE_DIFF12": "share_12m", "BEA_PCE_DIFF6": "share_6m"}


def _prices(table: str = PRICE_TABLE) -> pd.DataFrame:
    if not config.BEA_API_KEY:
        raise RuntimeError("BEA_API_KEY is not set in us-monitor/.env.")
    params = {"UserID": config.BEA_API_KEY, "method": "GetData",
              "DatasetName": "NIUnderlyingDetail", "TableName": table,
              "Frequency": "M", "Year": "ALL", "ResultFormat": "JSON"}
    r = requests.get(BEA_URL, params=params, timeout=120)
    r.raise_for_status()
    payload = r.json()["BEAAPI"]["Results"]
    if "Data" not in payload:
        raise RuntimeError(f"BEA returned no data: {payload.get('Error', payload)}")
    d = pd.DataFrame(payload["Data"])
    d["value"] = pd.to_numeric(d["DataValue"].astype(str).str.replace(",", ""), errors="coerce")
    d["date"] = pd.to_datetime(d["TimePeriod"].str.replace("M", "-") + "-01", errors="coerce")
    return d.dropna(subset=["date"])[["SeriesCode", "date", "value"]]


def fetch_diffusion(threshold: float = config.DIFFUSION_THRESHOLD,
                    include_codes: set[str] | None = None) -> pd.DataFrame:
    """Share (%) of PCE components with price growth above ``threshold``.

    Returns columns ``share_12m`` (y/y) and ``share_6m`` (6m annualized).
    """
    px = _prices()
    if include_codes:
        px = px[px["SeriesCode"].isin(include_codes)]
    px = px.pivot_table(index="date", columns="SeriesCode", values="value").sort_index()
    chg12 = px.pct_change(12, fill_method=None) * 100
    chg6 = ((px / px.shift(6)) ** 2 - 1) * 100

    def share(chg: pd.DataFrame) -> pd.Series:
        valid = chg.notna()
        return ((chg > threshold) & valid).sum(axis=1) / valid.sum(axis=1) * 100

    return pd.DataFrame({"share_12m": share(chg12), "share_6m": share(chg6)}).dropna(how="all")

