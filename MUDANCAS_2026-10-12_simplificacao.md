# Simplificação — 12/10/2026

## Por quê
Havia três mecanismos para atualizar os mesmos dados: o cache com validade de 12 h
(baixava sozinho ao abrir), os scripts `atualizar_dados` e os botões do painel.
Além disso, os dados ficavam em três lugares (cache por série, store e um arquivo
só com datas de divulgação), alternados por uma chave `live`/`stored`. Isso criava
a fraqueza encontrada: com a FRED inacessível e o cache vencido, os gráficos
quebravam em vez de mostrar o último dado bom.

## Como desfazer
- **Tudo:** apague a pasta `us-monitor` (guarde o `.env`) e descompacte
  `../us-monitor_backup_antes_simplificacao_20261012.zip` no mesmo lugar. O zip
  contém código e dados de antes da mudança (sem `.venv`).
- **Só um item:** cada linha abaixo diz o arquivo; a versão antiga está no zip.

## O que mudou

| # | Mudança | Arquivos | Efeito para quem usa |
|---|---|---|---|
| 1 | **Fim da atualização automática de 12 h.** O painel só lê o que está salvo; nada é baixado sozinho ao abrir. | `src/data.py`, `src/config.py` (saíram `CACHE_MAX_AGE_HOURS` e `DATA_MODE`) | Os dados só mudam quando você clica num botão. |
| 2 | **Download que falha mantém o dado anterior** (a fraqueza). Testado simulando a FRED fora do ar. | `src/data.py`, `src/store.py` | Sem internet/proxy bloqueado, o painel segue funcionando com o último dado. |
| 3 | **Um só lugar para os dados:** `data/store/` (`observations.parquet` + `metadata.parquet` com data de divulgação e de coleta). | `src/store.py` reescrito; **removidos** `src/cache.py`, os arquivos `data/<SERIE>.parquet` e `data/release_meta.parquet` (dados migrados para o store antes de apagar) | Nenhum. |
| 4 | **Fim do modo `live`/`stored`.** Os botões de atualizar aparecem se houver `FRED_API_KEY` no `.env`; sem chave, o painel é só leitura. | `src/dashboard/app.py`, `src/dashboard/ui.py`, `src/dashboard/tabs/fedspeak.py` | A variável `US_MONITOR_DATA_MODE` deixou de existir (`US_MONITOR_STORE_PATH` continua). |
| 5 | **Removidos os scripts `atualizar_dados.command/.bat`.** No lugar, botão **↻ Refresh all data** na barra lateral (séries + Fed speakers, ≈4–6 min). Os botões por aba continuam. | `atualizar_dados.*` apagados; `abrir_dashboard.*` sem o aviso que apontava para eles | Atualizar tudo agora é pelo painel. |
| 6 | **Instalação nova:** sem dados, o painel mostra "clique em Refresh all data" (ou, sem chave, pede as chaves no `.env`). | `src/dashboard/app.py` | Antes baixava série a série enquanto desenhava os gráficos. |
| 7 | **Job de ingestão virou 1 linha:** `python -m src.jobs.ingest` = mesmo que "Refresh all data" (útil para agendador/Databricks). | `src/jobs/ingest.py` (123 → 27 linhas) | Nenhum. |
| 8 | **BEA sem cache próprio** (a difusão do PCE é baixada junto com as séries). | `src/ingest/bea.py` | Nenhum. |
| 9 | **Código morto removido:** placeholders `src/ingest/market_path.py` e `src/ingest/fomc.py` (eram só `NotImplementedError`; continuam no roadmap do `CLAUDE.md`), `indicators.zscore`, `config.series_by_block`. | — | Nenhum. |
| 10 | Aba Fed Speakers: o botão duplicado "Fetch now" (estado vazio) saiu; usa o "Refresh all data". | `src/dashboard/tabs/fedspeak.py` | Nenhum. |
| 11 | Documentação atualizada. | `CLAUDE.md`, `README.md` | — |

## O que foi testado
- Painel completo: 11 abas, 65 gráficos, 0 erros (antes e depois iguais).
- Falha de download simulada: série mantida, data de coleta inalterada.
- Botão da aba Fiscal: 7/7 séries atualizadas.
- "Atualizar tudo" de ponta a ponta: 102/102 séries + Fed speakers (3 min 41 s).
- Instalação nova (store vazio), sem chave e sem dados, sem chave com dados (só leitura): mensagens corretas, sem erro.

## Mantido de propósito
- A camada opcional do Claude (`src/ingest/llm.py`): só é usada com `ANTHROPIC_API_KEY`; sem ela, nada muda.
- Os botões por aba e a tabela de séries no rodapé.

---

# Pacote de exportação + instalador — 12/10/2026 (mais tarde)

| # | Mudança | Arquivos | Como desfazer |
|---|---|---|---|
| 12 | **Instalação separada da abertura.** `instalar.command/.bat` (rodar 1 vez): cria `.venv`, instala `requirements.txt`, cria o `.env` a partir do `.env.example`. `abrir_dashboard.*` agora só abre (e avisa se o ambiente não existir). | novos: `instalar.command`, `instalar.bat`; reescritos: `abrir_dashboard.command`, `abrir_dashboard.bat` | versões antigas dos `abrir_dashboard.*` estão no zip de backup (eles instalavam sozinhos na 1ª vez) |
| 13 | **Windows usa `.venv`** (antes `.venv-win`, que só servia para pasta compartilhada entre Mac e Windows). | `instalar.bat`, `abrir_dashboard.bat` | idem |
| 14 | README: seção "Iniciar sem terminal" atualizada. | `README.md` | — |

**Pacote para outro computador:** `../us-monitor_export_20261012.zip` (83 KB) — só código,
`reference/`, `requirements.txt`, `.env.example`, instaladores e documentação. Sem `.venv`,
sem `data/`, sem `.env` (nenhuma chave dentro), sem este log.

Testado numa pasta limpa: instalar (46 s) → abrir sem chaves (pede as chaves) → com chaves
(pede "Refresh all data") → Refresh all (102/102 séries + 86 discursos) → painel completo,
11 abas, 0 erros. O `.bat` não pôde ser executado aqui (sem Windows); só formato conferido.
