@echo off
REM ==== Instala o US Monitor no Windows - rodar UMA vez (duplo clique) ====
REM Cria o ambiente Python (.venv), instala as dependencias e prepara o .env.
cd /d "%~dp0"

set PY=
py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>nul && set PY=py -3
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>nul && set PY=python
if not defined PY (
  echo Python 3.9 ou mais novo nao encontrado. Instale em https://www.python.org/downloads/windows/
  echo Na instalacao, marque "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% --version

%PY% -m venv .venv
if errorlevel 1 (
  echo Falha ao criar o .venv
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  echo Falha ao atualizar o pip ^(sem acesso ao pypi.org?^)
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Falha ao instalar as dependencias
  pause
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Criei o arquivo .env: cole nele suas chaves FRED_API_KEY e BEA_API_KEY e salve.
  echo ^(gratuitas: https://fred.stlouisfed.org/docs/api/api_key.html e https://apps.bea.gov/api/signup/^)
  notepad .env
)

echo.
echo Instalacao concluida.
echo Proximo passo: abrir_dashboard.bat e, no painel, clicar em "Refresh all data" ^(baixa os dados, ~5 min, so na 1a vez^).
pause
