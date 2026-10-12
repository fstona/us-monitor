#!/bin/bash
# ==== Abre o US Monitor no navegador (macOS). Duplo clique; Ctrl+C ou fechar a janela encerra ====
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/streamlit ]; then
  echo "Ambiente não instalado. Rode primeiro instalar.command."
  read -p "Enter para fechar"; exit 1
fi
echo "Abrindo o US Monitor... (feche esta janela ou Ctrl+C para encerrar)"
exec .venv/bin/streamlit run src/dashboard/app.py --browser.gatherUsageStats false
