#!/bin/bash
# ==== Instala o US Monitor no macOS — rodar UMA vez (duplo clique) ====
# Cria o ambiente Python (.venv), instala as dependências e prepara o .env.
cd "$(dirname "$0")" || exit 1
pause() { [ -z "$NOPAUSE" ] && read -p "Enter para fechar"; }

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v $c >/dev/null 2>&1 && $c -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    PY=$c; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.9 ou mais novo não encontrado. Instale em https://www.python.org/downloads/macos/"
  pause; exit 1
fi
echo "Usando $($PY --version) em $(command -v $PY)"

$PY -m venv .venv || { echo "Falha ao criar o .venv"; pause; exit 1; }
.venv/bin/python -m pip install --upgrade pip || { echo "Falha ao atualizar o pip (sem acesso ao pypi.org?)"; pause; exit 1; }
.venv/bin/python -m pip install -r requirements.txt || { echo "Falha ao instalar as dependências"; pause; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Criei o arquivo .env: cole nele suas chaves FRED_API_KEY e BEA_API_KEY e salve."
  echo "(gratuitas: https://fred.stlouisfed.org/docs/api/api_key.html e https://apps.bea.gov/api/signup/)"
  [ -z "$NOPAUSE" ] && open -e .env
fi

echo
echo "Instalação concluída."
echo "Próximo passo: abrir_dashboard.command e, no painel, clicar em '↻ Refresh all data' (baixa os dados, ~5 min, só na 1ª vez)."
pause
