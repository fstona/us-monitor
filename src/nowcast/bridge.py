"""CPI/PPI → PCE bridge (spec §4.3).

    contrib_i(t) = w_i(t-1) × π_i(t)        w_i = signed nominal share of line i in the
                                             aggregate (core or headline) at t-1
    π_agg(t)    ≈ Σ_i contrib_i(t)           chained-Fisher approximation

π_i comes from the line's source index (CPI/PPI/proxy) when it is available for t,
otherwise from the stage-0 prior. Pure functions: inputs in, frames out.
"""
from __future__ import annotations

import pandas as pd

BLOCKS = ["core_goods", "housing", "health", "core_services", "food", "energy"]


def source_changes(conc: pd.DataFrame, src_mm: pd.DataFrame) -> pd.DataFrame:
    """m/m % change per PCE line implied by its source(s); "a|b" = equal-weighted mean.
    ``src_mm``: dates × series_id (already seasonally treated). Prior lines → NaN."""
    out = {}
    for r in conc.itertuples():
        ids = [s for s in str(r.series_id).split("|") if s and s != "nan"]
        have = [s for s in ids if s in src_mm.columns]
        out[r.pce_line] = src_mm[have].mean(axis=1, skipna=False) if have and len(have) == len(ids) \
            else pd.Series(float("nan"), index=src_mm.index)
    return pd.DataFrame(out)


def weights(conc: pd.DataFrame, nominal: pd.Series, core: bool) -> pd.Series:
    """Signed nominal shares at one date (nominal: PCE line → $), summing to 1."""
    c = conc[conc.in_core] if core else conc
    v = nominal.reindex(c.pce_line).fillna(0.0).to_numpy() * c.sign.to_numpy()
    return pd.Series(v / v.sum(), index=c.pce_line.to_numpy())


def nowcast(conc: pd.DataFrame, nominal_prev: pd.Series, line_mm: pd.Series) -> dict:
    """One month. ``line_mm``: PCE line → m/m % (source or prior). Returns core and
    headline m/m plus contributions by block (pp)."""
    out = {}
    for name, core in (("core", True), ("headline", False)):
        w = weights(conc, nominal_prev, core)
        mm = line_mm.reindex(w.index)
        mm[w == 0] = 0.0                      # lines with no spending carry no information
        contrib = w * mm
        blocks = conc.set_index("pce_line").loc[w.index, "block"]
        out[name] = float(contrib.sum(min_count=len(contrib)))
        out[f"{name}_blocks"] = contrib.groupby(blocks.to_numpy()).sum().reindex(BLOCKS).dropna().to_dict()
    return out
