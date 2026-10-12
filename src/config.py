"""Central configuration: project paths, secrets, policy parameters and the
series catalog.

The catalog is the single source of truth for what the monitor tracks. Each
series carries enough metadata (native units, frequency, display transform,
source) that the ingestion job and the dashboard handle it without per-series
hard-coding. ALWAYS verify a new series' scale/frequency/coverage on FRED
before trusting it (see CLAUDE.md -> "Data gotchas").
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# --- Secrets ---------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")
FRED_API_KEY = os.getenv("FRED_API_KEY")
BEA_API_KEY = os.getenv("BEA_API_KEY")

# --- Policy parameters (defaults; some exposed as dashboard sliders) -------
INFLATION_TARGET = 2.0      # Fed's PCE target, %
DEFAULT_R_STAR = 0.75       # neutral real rate assumption, %
DEFAULT_RHO = 0.85          # interest-rate smoothing for the inertial rule
OKUN_COEF = 2.0             # output-gap points per pt of unemployment gap

# Approximate BLS relative-importance weights as a SHARE OF CORE CPI (~2024).
# Used to split core CPI into Powell's three buckets; supercore is the residual
# so the contributions sum exactly to core. Verify/refresh from BLS annually.
CPI_CORE_WEIGHTS = {"goods": 0.23, "shelter": 0.44}  # supercore ≈ 0.33 (residual)

# PCE diffusion (Warsh, Jackson Hole 2026): share of PCE components with price
# growth above this threshold, and the reference levels he quoted.
DIFFUSION_THRESHOLD = 3.0
DIFFUSION_PRE_PANDEMIC = 32.0   # avg share, two decades pre-pandemic
DIFFUSION_PEAK = 77.0           # post-pandemic peak

# --- Data store ------------------------------------------------------------
# Where the dashboard reads its data (see src/store.py). Override with an env
# var to point at shared storage (e.g. a Databricks UC Volume).
STORE_PATH = Path(os.getenv("US_MONITOR_STORE_PATH", str(DATA_DIR / "store")))


@dataclass(frozen=True)
class Series:
    id: str             # FRED series ID (or a derived ID for non-FRED sources)
    label: str          # human-readable name
    block: str          # thematic block (see BLOCKS)
    units: str = ""     # note on native units
    freq: str = ""      # native frequency: D, W, M, Q, A
    transform: str = "level"  # headline display: level|yoy|mom_diff|ann3m|ann6m
    source: str = "fred"      # fred | bea


# --- Series catalog --------------------------------------------------------
# NOTE: some Fed-bank series IDs are easy to get wrong. Verify on fred.org.
SERIES: list[Series] = [
    # ---- Inflation: realized ------------------------------------------------
    Series("PCEPILFE", "Core PCE price index", "inflation", "index 2017=100", "M", "yoy"),
    Series("PCEPI", "Headline PCE price index", "inflation", "index 2017=100", "M", "yoy"),
    Series("CPILFESL", "Core CPI", "inflation", "index 1982-84=100", "M", "yoy"),
    Series("CPIAUCSL", "Headline CPI", "inflation", "index 1982-84=100", "M", "yoy"),
    Series("PPIFIS", "PPI final demand", "inflation", "index", "M", "yoy"),
    Series("PPIACO", "PPI all commodities", "inflation", "index 1982=100", "M", "yoy"),
    Series("DCOILWTICO", "WTI crude oil", "inflation", "$/bbl", "D", "level"),
    # ---- Inflation: underlying (already 12m/6m %, don't re-transform) --------
    Series("PCETRIM12M159SFRBDAL", "Trimmed-mean PCE (12m)", "inflation", "% 12-mo", "M", "level"),
    Series("PCETRIM6M680SFRBDAL", "Trimmed-mean PCE (6m ann.)", "inflation", "% 6-mo ann.", "M", "level"),
    Series("MEDCPIM159SFRBCLE", "Cleveland median CPI (12m)", "inflation", "% 12-mo", "M", "level"),
    Series("TRMMEANCPIM159SFRBCLE", "Cleveland 16% trimmed-mean CPI (12m)", "inflation", "% 12-mo", "M", "level"),
    Series("CORESTICKM159SFRBATL", "Sticky-price CPI ex food/energy", "inflation", "% 12-mo", "M", "level"),
    # ---- Inflation: decomposition inputs ------------------------------------
    Series("CUSR0000SACL1E", "CPI core goods", "inflation", "index", "M", "yoy"),
    Series("CUSR0000SASLE", "CPI core services", "inflation", "index", "M", "yoy"),
    Series("CUSR0000SAH1", "CPI shelter", "inflation", "index", "M", "yoy"),
    Series("CPIENGSL", "CPI energy", "inflation", "index", "M", "yoy"),
    Series("IA001260M", "PCE supercore (services ex energy & housing)", "inflation", "index", "M", "yoy"),
    # ---- Inflation: breadth (computed from BEA Table 2.4.4U) ----------------
    Series("BEA_PCE_DIFF12", "PCE components > 3% (12m)", "inflation", "% of components", "M", "level", "bea"),
    Series("BEA_PCE_DIFF6", "PCE components > 3% (6m ann.)", "inflation", "% of components", "M", "level", "bea"),

    # ---- Inflation expectations -------------------------------------------
    Series("MICH", "UMich 1y inflation expectation", "expectations", "%", "M", "level"),
    Series("EXPINF1YR", "Cleveland Fed 1y expected inflation", "expectations", "%", "M", "level"),
    Series("EXPINF5YR", "Cleveland Fed 5y expected inflation", "expectations", "%", "M", "level"),
    Series("T5YIFR", "5y5y forward breakeven", "expectations", "%", "D", "level"),
    Series("T10YIE", "10y breakeven inflation", "expectations", "%", "D", "level"),

    # ---- Labor ------------------------------------------------------------
    Series("PAYEMS", "Nonfarm payrolls", "labor", "thousands", "M", "mom_diff"),
    Series("UNRATE", "Unemployment rate (U-3)", "labor", "%", "M", "level"),
    Series("U6RATE", "Underemployment (U-6)", "labor", "%", "M", "level"),
    Series("CIVPART", "Labor force participation", "labor", "%", "M", "level"),
    Series("LNS12300060", "Prime-age (25-54) employment-population", "labor", "%", "M", "level"),
    Series("JTSJOL", "Job openings (JOLTS)", "labor", "thousands", "M", "level"),
    Series("JTSJOR", "Job openings rate (JOLTS)", "labor", "%", "M", "level"),
    Series("JTSQUR", "Quits rate (JOLTS)", "labor", "%", "M", "level"),
    Series("ICSA", "Initial jobless claims", "labor", "number", "W", "level"),
    Series("IC4WSA", "Initial claims (4-wk avg)", "labor", "number", "W", "level"),
    Series("CCSA", "Continuing claims", "labor", "number", "W", "level"),
    Series("UNEMPLOY", "Unemployed persons", "labor", "thousands", "M", "level"),
    Series("CLF16OV", "Civilian labor force", "labor", "thousands", "M", "level"),
    # ---- Wages & unit labor costs (Clarida's lens) -------------------------
    Series("CES0500000003", "Avg hourly earnings", "labor", "$/hour", "M", "yoy"),
    Series("ECIALLCIV", "Employment Cost Index", "labor", "index", "Q", "yoy"),
    Series("ECIWAG", "ECI wages & salaries", "labor", "index", "Q", "yoy"),
    Series("FRBATLWGT3MMAUMHWGO", "Atlanta Wage Growth Tracker (3m MA)", "labor", "% median", "M", "level"),
    Series("ULCNFB", "Unit labor costs (nonfarm business)", "labor", "index", "Q", "yoy"),
    Series("OPHNFB", "Productivity (output per hour)", "labor", "index", "Q", "yoy"),
    Series("COMPNFB", "Compensation per hour", "labor", "index", "Q", "yoy"),

    # ---- Activity ---------------------------------------------------------
    Series("A191RL1Q225SBEA", "Real GDP growth (q/q ann.)", "activity", "%", "Q", "level"),
    Series("GDPNOW", "Atlanta Fed GDPNow", "activity", "% q/q ann.", "Q", "level"),
    Series("GDPC1", "Real GDP", "activity", "$ bn chained 2017", "Q", "yoy"),
    Series("GDP", "Nominal GDP", "activity", "$ bn SAAR", "Q", "yoy"),
    Series("GDPPOT", "Real potential GDP (CBO)", "activity", "$ bn chained 2017", "Q", "level"),
    Series("LB0000031Q020SBEA", "PDFP — real final sales to private domestic purchasers", "activity", "$ bn 2017", "Q", "yoy"),
    Series("Y033RX1Q020SBEA", "Real investment: equipment", "activity", "$ bn chained 2017", "Q", "yoy"),
    Series("Y001RX1Q020SBEA", "Real investment: intellectual property", "activity", "$ bn chained 2017", "Q", "yoy"),
    Series("PCEC96", "Real personal consumption", "activity", "$ bn chained 2017", "M", "yoy"),
    Series("RSAFS", "Retail sales", "activity", "$ millions", "M", "yoy"),
    Series("INDPRO", "Industrial production", "activity", "index 2017=100", "M", "yoy"),
    Series("TCU", "Capacity utilization", "activity", "%", "M", "level"),
    Series("HOUST", "Housing starts", "activity", "thousands SAAR", "M", "level"),
    Series("PERMIT", "Building permits", "activity", "thousands SAAR", "M", "level"),
    Series("UMCSENT", "UMich consumer sentiment", "activity", "index 1966Q1=100", "M", "level"),
    Series("CPATAX", "Corporate profits after tax", "activity", "$ bn SAAR", "Q", "yoy"),

    # ---- Rates (policy + Treasury curve) ------------------------------------
    Series("DFEDTARU", "Fed funds target (upper)", "rates", "%", "D", "level"),
    Series("DFEDTARL", "Fed funds target (lower)", "rates", "%", "D", "level"),
    Series("FEDFUNDS", "Effective fed funds rate", "rates", "%", "M", "level"),
    Series("NROU", "Natural rate of unemployment (CBO)", "rates", "%", "Q", "level"),
    Series("DGS3MO", "3-month Treasury", "rates", "%", "D", "level"),
    Series("DGS2", "2y Treasury", "rates", "%", "D", "level"),
    Series("DGS5", "5y Treasury", "rates", "%", "D", "level"),
    Series("DGS10", "10y Treasury", "rates", "%", "D", "level"),
    Series("DGS30", "30y Treasury", "rates", "%", "D", "level"),
    Series("DFII5", "5y TIPS real yield", "rates", "%", "D", "level"),
    Series("DFII10", "10y TIPS real yield", "rates", "%", "D", "level"),
    Series("THREEFYTP10", "10y term premium (Kim-Wright)", "rates", "%", "D", "level"),
    Series("T10Y2Y", "Yield curve 10y-2y", "rates", "%", "D", "level"),
    Series("T10Y3M", "Yield curve 10y-3m", "rates", "%", "D", "level"),
    Series("MORTGAGE30US", "30y mortgage rate", "rates", "%", "W", "level"),

    # ---- Credit & risk ----------------------------------------------------
    Series("BAMLH0A0HYM2", "High-yield OAS", "credit", "%", "D", "level"),
    Series("BAMLC0A0CM", "Investment-grade OAS", "credit", "%", "D", "level"),
    Series("VIXCLS", "VIX", "credit", "index", "D", "level"),
    Series("SP500", "S&P 500", "credit", "index", "D", "level"),
    Series("NFCI", "Chicago Fed NFCI", "credit", "index (0=avg)", "W", "level"),
    Series("DRTSCILM", "SLOOS: net % tightening C&I standards", "credit", "net %", "Q", "level"),
    Series("TOTCI", "C&I loans", "credit", "$ bn", "W", "yoy"),

    # ---- Dollar & FX (H.10 lags ~1 week) -----------------------------------
    Series("DTWEXBGS", "Broad dollar index", "fx", "index Jan-2006=100", "D", "level"),
    Series("DTWEXAFEGS", "Dollar vs advanced economies", "fx", "index Jan-2006=100", "D", "level"),
    Series("DTWEXEMEGS", "Dollar vs emerging markets", "fx", "index Jan-2006=100", "D", "level"),
    Series("DEXUSEU", "EUR/USD (USD per EUR)", "fx", "USD per EUR", "D", "level"),
    Series("DEXJPUS", "USD/JPY", "fx", "JPY per USD", "D", "level"),
    Series("DEXCHUS", "USD/CNY", "fx", "CNY per USD", "D", "level"),
    Series("DEXMXUS", "USD/MXN", "fx", "MXN per USD", "D", "level"),
    Series("DEXBZUS", "USD/BRL", "fx", "BRL per USD", "D", "level"),

    # ---- Money & Fed balance sheet ----------------------------------------
    Series("M2SL", "M2 money stock", "money", "$ bn", "M", "yoy"),
    Series("M2V", "Velocity of M2", "money", "ratio", "Q", "level"),
    Series("WALCL", "Fed total assets", "money", "$ millions", "W", "level"),
    Series("WRESBAL", "Reserve balances", "money", "$ millions", "W", "level"),
    Series("WTREGEN", "Treasury General Account (TGA)", "money", "$ millions", "W", "level"),
    Series("RRPONTSYD", "Overnight reverse repo (ON RRP)", "money", "$ bn", "D", "level"),

    # ---- Fiscal -----------------------------------------------------------
    Series("MTSDS133FMS", "Federal surplus/deficit (monthly, MTS)", "fiscal", "$ millions", "M", "level"),
    Series("FYGFDPUN", "Federal debt held by the public", "fiscal", "$ millions", "Q", "level"),
    Series("GFDEGDQ188S", "Total public debt (% of GDP)", "fiscal", "% of GDP", "Q", "level"),
    Series("A091RC1Q027SBEA", "Federal interest payments", "fiscal", "$ bn SAAR", "Q", "level"),
    Series("FGRECPT", "Federal current receipts", "fiscal", "$ bn SAAR", "Q", "level"),

    # ---- Reference ----------------------------------------------------------
    Series("USREC", "NBER recession indicator", "reference", "0/1", "M", "level"),
]

SERIES_BY_ID: dict[str, Series] = {s.id: s for s in SERIES}

# Curated market-moving macro releases for the Overview summary, in roughly the
# order one reads a data calendar. Each entry: (series_id, short name, hawkish
# sign). hawkish_sign = +1 if a HIGHER reading pushes the Fed hawkish (toward
# higher-for-longer), -1 if it pushes dovish (toward cuts). Drives the
# "what's new" feed and the hawkish/dovish scorecard; excludes daily financials.
HEADLINE_RELEASES: list[tuple[str, str, int]] = [
    ("PAYEMS", "Nonfarm payrolls", +1),
    ("UNRATE", "Unemployment rate", -1),
    ("JTSJOL", "Job openings (JOLTS)", +1),
    ("JTSQUR", "Quits rate", +1),
    ("ICSA", "Initial jobless claims", -1),
    ("CES0500000003", "Avg hourly earnings", +1),
    ("ECIALLCIV", "Employment Cost Index", +1),
    ("CPILFESL", "Core CPI", +1),
    ("CPIAUCSL", "Headline CPI", +1),
    ("PCEPILFE", "Core PCE", +1),
    ("PCETRIM12M159SFRBDAL", "Trimmed-mean PCE", +1),
    ("PPIFIS", "PPI final demand", +1),
    ("MICH", "UMich 1y inflation exp.", +1),
    ("RSAFS", "Retail sales", +1),
    ("A191RL1Q225SBEA", "Real GDP (q/q ann.)", +1),
    ("LB0000031Q020SBEA", "PDFP (y/y)", +1),
    ("INDPRO", "Industrial production", +1),
    ("UMCSENT", "Consumer sentiment", +1),
]

# Display names for each block (used in the release scorecard).
BLOCK_NAMES = {
    "inflation": "Inflation", "expectations": "Inflation", "labor": "Labor",
    "activity": "Activity", "rates": "Rates", "credit": "Credit",
    "fx": "Dollar", "money": "Money", "fiscal": "Fiscal",
}
