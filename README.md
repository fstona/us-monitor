# US Monitor

Interactive dashboard of the US economy — **rates, market prices, the dollar,
inflation, activity and fiscal** — read through the Fed's dual mandate.
Merges `fed-monitor` (architecture, policy rules, inflation/labor frameworks)
with the analyses from Chair Warsh's Jackson Hole 2026 keynote (`Warsh_dash`).

## Tabs

| Tab | What it answers |
|---|---|
| **Overview** | Snapshot by area · rule benchmark · release scorecard · ★ Warsh checklist |
| **Fed Speakers** | 19 participants: ITC hawk scale, speech tone (90d), latest remarks, voter ✓/✗ for 3 years · next-7-days calendar · blackout · speech feed with summaries |
| **Inflation** | Level, 12m/6m/3m momentum, trimmed-mean/median, ★ breadth (BEA diffusion), three buckets, commodities, expectations |
| **Labor** | Payrolls & claims, Michaillat–Saez tightness, Beveridge curve, supply, wages & ULC |
| **Activity** | GDP & GDPNow, ★ PDFP, capex (AI), consumer, industry, housing, profits |
| **Rates** | Real policy rate vs r*, what markets price (2y − FF), curve, 10y = real + breakeven, term premium |
| **Credit & Risk** | HY/IG spreads, VIX, S&P 500, NFCI, SLOOS, C&I loans |
| **Dollar & FX** | Scoreboard (1m/3m/YTD/1y), broad/AFE/EM, EUR/JPY/CNY/MXN/BRL |
| **Money & Liquidity** | M2 vs nominal GDP, velocity, Fed balance sheet & net liquidity |
| **Fiscal** | 12m deficit % GDP, debt, interest burden, r vs g |
| **Policy Rules** | Taylor / balanced / inertial, history and 2-year scenario |

## Iniciar sem terminal

| | Mac | Windows |
|---|---|---|
| 1ª vez: instala o ambiente (`.venv`) e cria o `.env` | `instalar.command` | `instalar.bat` |
| Abrir o painel | `abrir_dashboard.command` | `abrir_dashboard.bat` |

Duplo clique. Requer Python 3.9+ instalado e acesso ao pypi.org na instalação. O
instalador cria o `.env` e o abre para você colar as chaves (FRED e BEA, gratuitas).
No primeiro uso o painel está vazio: clique em **↻ Refresh all data** na barra
lateral (~5 min). Depois, os dados só mudam quando você pede — botão de cada aba ou
"Refresh all data". Se um download falhar, o dado anterior é mantido.

## Baixar do GitHub (outro computador)

1. Na página do repositório: **Code → Download ZIP**.
2. **Windows:** antes de descompactar, clique com o botão direito no zip →
   *Propriedades* → marque **Desbloquear** → OK. Sem isso, o Windows pode exibir
   "O Windows protegeu o computador" ao abrir o `.bat` (nesse caso: *Mais
   informações* → *Executar assim mesmo*). **Mac:** na primeira vez, clique com o
   botão direito no `.command` → *Abrir* → *Abrir*.
3. Rode o instalador e depois o `abrir_dashboard` (tabela acima).

Se a política da empresa bloquear `.bat`, os mesmos passos funcionam no terminal:
`py -3 -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`,
`.venv\Scripts\streamlit run src\dashboard\app.py`.

## Setup (manual, via terminal)

```bash
cd us-monitor
cp .env.example .env          # FRED_API_KEY, BEA_API_KEY (+ optional ANTHROPIC_API_KEY)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/dashboard/app.py
# sem abrir o painel (ex.: agendador): python -m src.jobs.ingest  (= "Refresh all data")
```

See `CLAUDE.md` for architecture, data gotchas and the roadmap.

## Fontes

Dados: FRED (Federal Reserve Bank of St. Louis), BEA, Federal Reserve Board e
Reserve Banks, BIS. Escala hawk/dove dos participantes do FOMC: ITC Markets
Research, *FOMC – ITC Hawk/Dove Analysis*, 14/09/2026 — ver `reference/README.md`.
