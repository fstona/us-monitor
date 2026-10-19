"""Live PCE nowcast — recomputes only when new inputs have been released.

    update()  →  checks the latest CPI / PPI month (one light BLS query) and the
                 latest PCE month in the store; if nothing changed since the last
                 run, returns immediately. Otherwise downloads the PCE detail (BEA)
                 and the source indices (BLS), runs the bridge and appends a row to
                 the store table ``nowcast_runs`` (the dashboard only reads it).

Model pieces come from the backtest in the lab (reference/ files, versioned):
concordance, seasonal factors for NSA sources, bias correction by stage, metrics.
Stage: 0 = prior only · 1 = CPI observed · 2 = CPI + PPI observed. If the PPI comes
out before the CPI, its lines are used but the run is reported as stage 0.
"""
from __future__ import annotations

import json

import pandas as pd

from src import config, data, store
from src.ingest import bea, bls
from src.nowcast import bridge, snapshots

REF = config.PROJECT_ROOT / "reference"
TABLE = "nowcast_runs"
BELLWETHER = {"cpi": "CUSR0000SEHA", "ppi": "PCU622---622---"}   # rent (CPI release) · hospitals (PPI release)
GAS_LINES = [115]                                               # gasoline and other motor fuel
STAGE_NAME = {0: "Prior", 1: "CPI", 2: "CPI + PPI"}
# FRED series the nowcast needs (PCE vintage, release dates, line-model regressors)
FRED_INPUTS = ["PCEPI", "PCEPILFE", "CPIAUCSL", "PPIFIS", "DGS3MO", "FEDFUNDS",
               "DFEDTARU", "DFEDTARL", "CES0500000003", "GASREGW"]
STAGES_OF = {"ppi_scaled": {2}, "rates": {0, 1, 2}, "wages": {1, 2}}   # as in the backtest


def _reference():
    conc = pd.read_csv(REF / "nowcast_concordance.csv")
    sf = pd.read_csv(REF / "nowcast_seasonal_factors.csv")
    bias = pd.read_csv(REF / "nowcast_bias.csv").set_index("stage")
    lm = pd.read_csv(REF / "nowcast_line_models.csv")
    return conc, sf, bias, lm


def runs() -> pd.DataFrame:
    try:
        return store.get_table(TABLE)
    except FileNotFoundError:
        return pd.DataFrame()


def _latest_months() -> dict:
    """Latest released month of PCE (store), CPI and PPI (one BLS query)."""
    year = pd.Timestamp.today().year
    b = bls.fetch(list(BELLWETHER.values()), year - 1, year)
    last = b.groupby("series_id").date.max()
    return {"pce": data.get_series("PCEPI").index.max(),
            "cpi": last[BELLWETHER["cpi"]], "ppi": last[BELLWETHER["ppi"]],
            "ahe": data.get_series("CES0500000003").index.max()}


def _gasoline_mm(target: pd.Timestamp) -> float | None:
    """m/m of the average weekly retail gasoline price (EIA data via FRED GASREGW)
    for the target month so far vs the previous month."""
    m = data.get_series("GASREGW").resample("MS").mean()
    if target not in m.index or target - pd.DateOffset(months=1) not in m.index:
        return None
    return float((m[target] / m[target - pd.DateOffset(months=1)] - 1) * 100)


def _inputs(months: dict) -> dict:
    """Download everything one target month needs (BEA detail + BLS sources)."""
    conc, sf, bias, lm = _reference()
    target = months["pce"] + pd.DateOffset(months=1)
    prev = target - pd.DateOffset(months=1)
    years = bea.recent_years(3)          # same request as the PCE diffusion → reused, not re-downloaded
    px = bea.fetch_table("U20404", years)
    nom = bea.fetch_table("U20405", years)
    snapshots.save("bea_pce_price", px); snapshots.save("bea_pce_nominal", nom)
    P = px.pivot_table(index="date", columns="LineNumber", values="value")
    N = nom.pivot_table(index="date", columns="LineNumber", values="value")
    if prev not in N.index:
        raise RuntimeError(f"BEA detail for {prev:%b %Y} not available yet — try again later.")

    ids = sorted({s for x in conc.series_id.dropna() for s in str(x).split("|") if s})
    src = bls.fetch(ids, target.year - 1, target.year)
    snapshots.save("bls_sources", src)
    s_mm = src.pivot(index="date", columns="series_id", values="value").pct_change(fill_method=None) * 100
    line_src = pd.Series(dtype=float)
    if target in s_mm.index:                                     # seasonal factors for NSA sources
        f = sf[sf.month == target.month].set_index("series_id").factor_pp
        row = s_mm.loc[[target]].copy()
        cols = [c for c in f.index if c in row.columns]
        row[cols] = row[cols] - f[cols].to_numpy()
        line_src = bridge.source_changes(conc, row).iloc[0]

    # stage-0 prior: trailing 12-month mean m/m of each PCE line; gasoline from weekly prices
    pce_mm = P.pct_change(fill_method=None) * 100
    prior = pce_mm[pce_mm.index < target].tail(12).mean()
    gas = _gasoline_mm(target)
    if gas is not None:
        prior[GAS_LINES] = gas
    return {"conc": conc, "bias": bias, "lm": lm, "P": P, "N": N, "target": target, "prev": prev,
            "line_src": line_src, "prior": prior, "reg": _regressors(target)}


def _regressors(target: pd.Timestamp) -> dict:
    """Line-model regressors for the target month, from the store (None if not out yet)."""
    def mavg(sid):
        return data.get_series(sid).resample("MS").mean()
    tb = mavg("DGS3MO").diff()
    ff = data.get_series("FEDFUNDS")
    if target not in ff.index:     # monthly EFFR not published yet → target-range midpoint
        mid = ((mavg("DFEDTARU") + mavg("DFEDTARL")) / 2)
        d_ff = mid.diff().get(target)
    else:
        d_ff = ff.diff().get(target)
    ahe = data.get_series("CES0500000003").pct_change() * 100
    get = lambda s, t: None if t not in s.index or pd.isna(s[t]) else float(s[t])   # noqa: E731
    return {"d_tbill": get(tb, target), "d_tbill_l1": get(tb, target - pd.DateOffset(months=1)),
            "d_ff": None if d_ff is None or pd.isna(d_ff) else float(d_ff), "ahe_mm": get(ahe, target)}


def _apply_line_models(inp: dict, mm: pd.Series, stage: int) -> pd.Series:
    """Replace lines with their validated models when the inputs exist at this stage."""
    for line, g in inp["lm"].groupby("pce_line"):
        kind = g.kind.iloc[0]
        if stage not in STAGES_OF[kind]:
            continue
        coef = g.set_index("term").coef
        x = {"own": inp["line_src"].get(line), **inp["reg"]}
        terms = [t for t in coef.index if t != "const"]
        if any(x.get(t) is None or pd.isna(x.get(t)) for t in terms):
            continue
        mm[line] = coef["const"] + sum(coef[t] * x[t] for t in terms)
    return mm


def _nowcast(inp: dict, use_cpi: bool, use_ppi: bool) -> dict:
    """One stage of the nowcast from the downloaded inputs."""
    conc, target, prev, P = inp["conc"], inp["target"], inp["prev"], inp["P"]
    observed = []
    if use_cpi:
        observed += conc[conc.stage_available == "cpi"].pce_line.tolist()
    if use_ppi:
        observed += conc[conc.stage_available == "ppi"].pce_line.tolist()
    mm = inp["prior"].reindex(conc.pce_line).copy()
    obs = inp["line_src"].reindex(observed).dropna()
    mm[obs.index] = obs
    stage = 2 if (use_cpi and use_ppi) else (1 if use_cpi else 0)
    mm = _apply_line_models(inp, mm, stage)
    o = bridge.nowcast(conc, inp["N"].loc[prev], mm)
    out = {"target": target, "stage": stage,
           "stage_name": STAGE_NAME[stage] if not (use_ppi and not use_cpi) else "Prior + PPI"}
    for agg, line in (("core", 374), ("headline", 1)):
        val = o[agg] + float(inp["bias"].loc[stage, f"{agg}_pp"])  # backtest bias correction
        level = P[line].loc[prev] * (1 + val / 100)
        out[f"{agg}_mm"] = round(val, 4)
        out[f"{agg}_yoy"] = round((level / P[line].loc[target - pd.DateOffset(months=12)] - 1) * 100, 3)
        out[f"{agg}_blocks"] = json.dumps({k: round(v, 4) for k, v in o[f"{agg}_blocks"].items()})
    return out


def _release_dates(target: pd.Timestamp, months: dict) -> dict:
    """When each input was published (FRED last-updated stamps in the store)."""
    info = data.release_info()
    def stamp(sid, ok):
        ts = info["last_updated"].get(sid) if ok and "last_updated" in info else None
        return None if ts is None or pd.isna(ts) else pd.Timestamp(ts)
    return {"pce": stamp("PCEPI", True),
            "cpi": stamp("CPIAUCSL", months["cpi"] >= target),
            "ppi": stamp("PPIFIS", months["ppi"] >= target)}


def compute_path(months: dict) -> list[dict]:
    """The nowcast after each release for the target month, in release order:
    last PCE → first of CPI/PPI → both."""
    inp = _inputs(months)
    target, prev = inp["target"], inp["prev"]
    when = _release_dates(target, months)
    now = pd.Timestamp.now(tz="UTC")
    events = [(f"PCE {prev:%b} released", when["pce"], False, False)]
    cpi_in, ppi_in = months["cpi"] >= target, months["ppi"] >= target
    first = sorted([(when["cpi"] or now, "cpi"), (when["ppi"] or now, "ppi")])
    if cpi_in and ppi_in:
        if first[0][0].normalize() != first[1][0].normalize():   # different days: keep the middle step
            k = first[0][1]
            events.append((f"{k.upper()} {target:%b} released", first[0][0], k == "cpi", k == "ppi"))
        events.append((f"{first[1][1].upper()} {target:%b} released", first[1][0], True, True))
    elif cpi_in or ppi_in:
        k = "cpi" if cpi_in else "ppi"
        events.append((f"{k.upper()} {target:%b} released", when[k], cpi_in, ppi_in))
    rows = []
    for event, date, use_cpi, use_ppi in events:
        r = _nowcast(inp, use_cpi, use_ppi)
        r.update({"event": event, "event_date": date, "run_at": now, "vintage_pce": months["pce"],
                  "vintage_cpi": months["cpi"], "vintage_ppi": months["ppi"], "vintage_ahe": months["ahe"]})
        rows.append(r)
    return rows


def update(force: bool = False, refresh_inputs: bool = True) -> str:
    """Recompute if new data came out; returns a one-line status for the UI.
    The whole path of the target month is rebuilt (one row per release).
    ``refresh_inputs=False`` when the caller already refreshed FRED_INPUTS."""
    if refresh_inputs:
        data.refresh(FRED_INPUTS)
    months = _latest_months()
    hist = runs()
    if not force and not hist.empty and "vintage_ahe" in hist:
        last = hist.iloc[-1]
        if (pd.Timestamp(last.vintage_pce), pd.Timestamp(last.vintage_cpi), pd.Timestamp(last.vintage_ppi),
                pd.Timestamp(last.vintage_ahe)) == (months["pce"], months["cpi"], months["ppi"], months["ahe"]):
            return f"PCE nowcast unchanged (no new CPI/PPI/PCE since {pd.Timestamp(last.run_at):%d %b %H:%M} UTC)."
    path = compute_path(months)
    target = path[0]["target"]
    if not hist.empty:
        hist = hist[pd.to_datetime(hist.target) != target]          # replace this month's path
    hist = pd.concat([hist, pd.DataFrame(path)], ignore_index=True)
    config.STORE_PATH.mkdir(parents=True, exist_ok=True)
    hist.to_parquet(config.STORE_PATH / f"{TABLE}.parquet", index=False)
    r = path[-1]
    return (f"PCE nowcast for {r['target']:%b %Y} updated — stage {r['stage_name']}: "
            f"core {r['core_mm']:+.2f}% m/m, headline {r['headline_mm']:+.2f}% m/m.")


def safe_update(refresh_inputs: bool = True) -> str:
    """update() for the UI/jobs: never raises; explains what went wrong."""
    try:
        return update(refresh_inputs=refresh_inputs)
    except Exception as exc:  # noqa: BLE001 — the previous nowcast stays in the store
        msg = str(exc)
        if "daily threshold" in msg:
            msg = "BLS daily request limit reached — add a free BLS_API_KEY to .env"
        return f"⚠️ PCE nowcast not updated ({msg[:160]}); showing the previous run."
