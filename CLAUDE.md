# CLAUDE.md — US Monitor

Project-specific guidance for working in this repo. (Global profile/preferences
live in the user's `~/.claude/CLAUDE.md`.)

## Goal

A complete dashboard of the US economy to draw conclusions about **rates,
market prices, the dollar, inflation, activity and fiscal**, anchored on the
Fed's dual mandate: what *should* the Fed do (policy-rule benchmark), what do
**markets price**, and which way is the **data** pushing.

Successor to two projects (kept untouched in sibling folders):
- `../fed-monitor` — the architecture (catalog → ingest → transform →
  dashboard; ingestion job), Powell's three buckets,
  Michaillat–Saez labor tightness, Clarida's ULC lens, Taylor-rule benchmark,
  release scorecard.
- `../Warsh_dash` — the analyses from Chair Warsh's Jackson Hole 2026 keynote
  ("In Our Time"): 12m vs 6m reads, trimmed-mean 6m, **PCE diffusion (BEA)**,
  commodities, three families of expectations, PDFP, capex/AI, profits,
  spreads, SLOOS, NFCI, claims, M2/velocity, dollar. They are folded into the
  thematic tabs (marked ★) — there is no separate "Warsh tab" — plus the
  **Warsh checklist** on the Overview (`transform/signals.py`).

## Stack & how to run

- **Python 3.9 venv** in `us-monitor/.venv`; Streamlit + Plotly; FRED
  (`fredapi`) and BEA (`requests`). Data cached to parquet under `data/`.
- Run from the project root: `streamlit run src/dashboard/app.py`.
- Populate/refresh the store (also fills the release dates on the Overview):
  `python -m src.jobs.ingest` (~5 min; paced for FRED's rate limit).
- Secrets: `FRED_API_KEY`, `BEA_API_KEY` in `us-monitor/.env` (gitignored;
  template in `.env.example`). Never commit keys.
- Streamlit 1.50: `st.plotly_chart` still needs `use_container_width=True`
  (`width="stretch"` is misread as a Plotly config kwarg); `st.dataframe`
  takes `width="stretch"`.

## Architecture (keep the layers separate)

```
refresh buttons / jobs.ingest ─> data.refresh ─> ingest/ (fred.py, bea.py) ─> store (data/store/*.parquet)
dashboard ─> ui.load ─> data.get_series ─> store            (reading never touches the network)
```

- `config.SERIES` is the **single source of truth**. Each `Series` has
  `block`, `freq`, headline `transform`, and `source` (`fred` | `bea`). Add a
  series there, then refresh: it is downloaded with the rest.
- **One data store, no automatic refresh.** `src.store` holds every series
  (`observations.parquet`) and its `last_updated`/`fetched_at`
  (`metadata.parquet`). The dashboard only *reads* it (`data.get_series`);
  data changes only via `data.refresh(ids)` — the per-tab buttons, the
  sidebar "Refresh all data" button, or `python -m src.jobs.ingest` (for a
  scheduler). A failed download leaves the stored series untouched.
  **Download only what changed:** `refresh` first reads FRED's last-updated stamp
  (one light call) and skips the observations if it matches the stored one; the
  BEA diffusion is recomputed only when a new PCE month exists, from the last 3
  years merged into the stored history. `bea.fetch_table` keeps a 10-minute cache
  so one click shares the U20404 table between the diffusion and the nowcast.
  Callers pass everything they need to ONE `refresh` call (the Inflation button
  adds `nowcast.run.FRED_INPUTS`, then runs the nowcast with `refresh_inputs=False`). Buttons
  appear only when `FRED_API_KEY` is set, so a key-less deployment (e.g.
  Databricks app with `US_MONITOR_STORE_PATH` on a UC Volume) is read-only.
  Never call `fredapi`/BEA from the dashboard or transforms.
- `transform/` is pure (series in, frames out): `indicators` (yoy, annualized,
  to_monthly, rebase, change_over), `inflation` (three buckets), `labor`
  (θ, FERU, gap), `rates` (real policy rate, 2y−FF, curve snapshot), `money`
  (Fed net liquidity), `fiscal` (12m balance % GDP, r vs g),
  `policy_rules`, `signals` (Warsh checklist).
- `dashboard/app.py` only wires the sidebar and tabs. Each tab is
  `dashboard/tabs/<name>.py` with `render()`. Shared helpers in
  `dashboard/ui.py` (`load` cached loader, `yoy`/`ann` using the catalog freq,
  `since()` global lookback, `guard()` per-chart error isolation, `metric`).
  Charts only via `dashboard/charts.py`.
- **Tab frame** (`ui.tab_frame(name)` in `app.py`): every catalog-series tab
  gets a header (🕒 data-fetched time + "↻ Refresh this tab")
  and a footer table of the series it used (latest observation, source
  release stamp, fetch time). Series are **recorded automatically** by
  `ui.load()`; code that reads data through *another* `st.cache_data`
  function must call `ui.track(*ids)` (a cache hit skips the inner loads —
  see `ui.labor_frame`, Overview's release scorecard). Per-tab refresh =
  `data.refresh(ids)`. Fed Speakers has its own refresh (the fed-speak job)
  and a *sources* footer instead.
- Wrap every chart/section in `with ui.guard("…"):` — a bad series warns
  locally instead of killing the tab.

## Fed Speakers tab (fed-speak)

- **Roster** `reference/fomc_roster.csv` (editable): 19 participants, `seat`
  (board / bank), `hawk_itc` = ITC Markets hawk scale (−1…+1, read from their
  14-Sep-2026 chart — refresh when ITC republishes). Voter status is
  **computed** from the statutory rotation (`transform/fomc.py`,
  `ROTATION_GROUPS` ordered from 2026) — never type it.
- **Blackout**: second Saturday before the meeting → day after it
  (`fomc.blackout_window`); meeting dates scraped from fomccalendars.htm.
- **Sources** (`ingest/fedspeak.py`): Board JSON (`/json/ne-speeches.json`,
  full list — the RSS only has 15), BIS RSS, and per-bank scrapers for NY,
  Boston, Philadelphia, Cleveland (slugs from embedded JSON), Richmond (RSS),
  Atlanta (JSON feed API), Chicago (date from URL slug; video-only pages →
  "No transcript"), Minneapolis, Dallas, SF. **St. Louis and Kansas City
  block scripted clients (Akamai)** — do not try to evade; they come only via
  BIS, the Claude web search, or `reference/fedspeak_remarks_manual.csv`.
- **Calendar**: Board `/json/calendar.json` (official: Governors, FOMC,
  Beige Book) + `reference/fedspeak_calendar_manual.csv` + Claude web search.
- **Tone**: `transform/fedspeak.py` lexicon (default; sentence-level
  hawk/dove phrases, score −2…+2 shrunk toward 0 with few hits; skews
  relative, not absolute) or `ingest/llm.py` (Claude Opus 5.5, structured
  output, refusal fallbacks on) when `ANTHROPIC_API_KEY` is set — the job then
  re-scores lexicon rows `RESCORE_PER_RUN` at a time.
- **Job** `python -m src.jobs.fedspeak` (also chained after `src.jobs.ingest`):
  incremental by URL; writes `fedspeak_speeches`, `fedspeak_calendar`,
  `fomc_meetings`, `fedspeak_status` parquet tables to STORE_PATH.
- The `anthropic` SDK is pinned `<1` because the venv is Python 3.9 (1.x needs
  3.10+). Rebuild the venv on 3.10+ before upgrading.

## PCE nowcast (spec: `nowcast_pce_spec.md`)

Bottom-up CPI/PPI → PCE bridge for next month's headline and core PCE (m/m,
first print). Lives inside the **Inflation** tab (section at the top + dotted
projections on the PCE charts).

- **Work/home split.** The live engine is in the repo (`src/nowcast/`); the
  research (concordance building, validation, backtest) stays on the Mac in
  `../us-monitor-lab/nowcast/` (not versioned). Only final artifacts cross over,
  all in `reference/`: `nowcast_concordance.csv` (224 PCE leaf lines → source),
  `nowcast_seasonal_factors.csv`, `nowcast_bias.csv`, `nowcast_backtest_metrics.csv`,
  `nowcast_line_models.csv`.
  To change the model: edit/run in the lab (`concordance_build.py`, `validate.py`,
  `backtest.py`, `export.py`), then commit the reference files.
- **Runs only on new data.** `nowcast.run.update()` checks the latest CPI/PPI
  month (one BLS query, bellwethers in the concordance) and the latest PCE month
  in the store; same vintage → no recompute. Called by the Inflation tab's refresh,
  "Refresh all data" and `jobs.ingest` (via `safe_update`, which never raises).
  Each run appends to the store table `nowcast_runs`; raw inputs are kept in
  `data/nowcast/snapshots/` (real-time track record).
- **Stages:** 0 prior (trailing-12m mean m/m per line; gasoline line from weekly
  retail gasoline) · 1 CPI · 2 CPI+PPI (PPI-only = reported as stage 0). Each
  update rebuilds the target month's **path** — one row per release (last PCE →
  first of CPI/PPI → both), dated with FRED's release stamps — so the chart shows
  the nowcast after each release even if you refresh only once.
- **Line models** (`reference/nowcast_line_models.csv`, from `lab/line_models.py`,
  validated out of sample): hospitals and air transport = scaled PPI (BEA passes
  ~75% / ~61% through); imputed banking (line 255) = ΔT-bill, ΔFF; NPISH (342) =
  AHE m/m (from stage 1, when the jobs report is out). Inputs are FRED series in
  the store, refreshed by `update()` itself (`FRED_INPUTS`).
- **Error budget** (`lab/error_decomp.py`): about half of the stage-2 error vs the
  first print is BEA's own later revision (revised − first ≈ 6 bps RMSE), so R² of
  the core cannot go much higher with this target. Portfolio management is the
  largest single line error vs *revised* data but does not improve vs the first
  print with equities or PPI lags — it is revision noise.
- **Model choices came from the backtest** (2015+, first-print target, ex Covid):
  NSA sources (all PPI services, NSA-only CPI items) seasonally adjusted with
  calendar-month factors — without it, adding the PPI *worsens* the nowcast;
  prior = 12m mean; bias correction by stage. Core RMSFE ≈ 6.3 bps at stage 2 (R² 0.73).
- **Gotchas:** BEA's API gives no line hierarchy → leaves come from BEA's
  `SeriesRegister.txt` parents ("Less:" lines flip their descendants' sign).
  Every BLS ID verified in the official catalogs (`bls.catalog`, needs
  `BLS_CONTACT_EMAIL`). CPI legal services was discontinued (Oct 2025) → PPI proxy.
  Portfolio management PPI = 523940-1 + 523940-2 (the aggregate only starts 2022).
  Without `BLS_API_KEY` the BLS allows 25 queries/day — enough for one or two
  nowcast refreshes; get the free key.
- The dashboard shows only the open target month (no past-month comparisons — Filipe
  prefers it clean).
- **Not yet:** EIA client (gasoline comes from FRED GASREGW, stored like any series, which republishes
  EIA's weekly price with ~1 day lag; switch when an EIA key exists), market-based
  PCE, reconstructing real-time CPI seasonal factors.

## Chart conventions (from both projects)

- Latest value in each legend label; NBER shading; dotted reference lines.
- **Never a dual y-axis** — different units go side by side (Warsh deck rule).
- `clip=0.02` trims the y-range by quantile so 2020 doesn't flatten recent data.
- ★ in a title/caption = analysis drawn from the Warsh keynote, with a short
  quote in the caption.

## Data gotchas (verify before trusting a series)

Mirror the `bcb-series` discipline — **check scale, frequency and coverage on
FRED before wiring a new series in**:

- **Index vs rate:** price indices need `yoy`; Dallas/Cleveland/Atlanta
  series are *already* 12m (or 6m ann.) percentages — don't re-transform.
- **CBO series (NROU, GDPPOT) run to ~2036** — use `ui.value_asof(id, date)`,
  never `.iloc[-1]`.
- **Units differ within a chart's inputs:** WALCL/WTREGEN/WRESBAL are $mn,
  RRPONTSYD $bn; MTSDS133FMS is a monthly $mn flow (not annualized);
  FYGFDPUN $mn; GDP/A091RC1Q027SBEA/FGRECPT $bn SAAR. Conversions live in
  `transform/money.py` and `transform/fiscal.py`.
- **ICE BofA spreads (HY/IG OAS) on FRED only go back ~3 years** (licensing).
  `SP500` only 10 years. Don't build long-history stats on them.
- **FX quotes:** DEXUSEU is USD per EUR; all other DEX* are foreign per USD.
  The FX tab normalizes everything to "+ = dollar stronger".
- **H.10 FX lags ~1 week; GDPNOW** on FRED is quarterly (final nowcast per quarter).
- **PCE diffusion** (`bea.py`) counts every line of BEA Table 2.4.4U
  (leaves + aggregates). It lands close to Warsh's 54% but is not the exact
  199-leaf count; pass `include_codes` for an exact match.
- **ISM PMIs are not freely on FRED** — left out.

## Frameworks encoded

- **Inflation:** Powell's three buckets (core goods · shelter · supercore;
  `config.CPI_CORE_WEIGHTS`, refresh from BLS yearly); momentum 12m/6m/3m;
  trimmed-mean/median (Warsh's preferred, with the 2021–22 caveat); breadth.
- **Labor:** Michaillat–Saez (θ = v/u, FERU = √(u·v)); Clarida's ULC lens.
- **Rules:** Taylor 1993, balanced approach, inertial; inflation gauge
  selectable (core PCE / trimmed mean / headline); r*, ρ in the sidebar.
- **Warsh checklist:** `transform/signals.py`; thresholds in `THRESHOLDS` are
  judgment calls — review them, don't treat as estimates.

## Roadmap (not all at once)

0. **Fed Speakers v2**: Claude classification on (needs ANTHROPIC_API_KEY);
   regional calendars scraped directly where pages allow; testimony feed;
   FOMC statement/minutes tone; dissent tracker.
1. **Market-implied path** (next priority): fed funds futures / SOFR
   futures or the Atlanta Fed Market Probability Tracker → cut/hold/hike
   probabilities; replaces the 2y−FF proxy.
2. **SEP dot plot** → rule vs dots vs market chart.
3. **Release calendar** (FRED releases API) on the Overview.
4. **Narrative deck export** — regenerate the Warsh-style 16:9 HTML deck
   (desktop + mobile) from this store instead of the standalone script.
5. Fiscal: CBO baseline projections; Treasury auction sizes/tails;
   term premium vs deficit.
6. Markets: equity valuation (ERP vs real 10y), oil curve, dollar vs rate
   differentials (needs foreign yields).
7. Databricks deployment (inherited plan from fed-monitor: job 2×/day →
   UC Volume, app read-only without keys).
