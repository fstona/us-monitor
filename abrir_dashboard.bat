@echo off
REM ==== Abre o US Monitor no navegador (Windows). Duplo clique; feche a janela para encerrar ====
cd /d "%~dp0"
if not exist .venv\Scripts\streamlit.exe (
  echo Ambiente nao instalado. Rode primeiro instalar.bat.
  pause
  exit /b 1
)
echo Abrindo o US Monitor... ^(feche esta janela para encerrar^)
.venv\Scripts\streamlit.exe run src\dashboard\app.py --browser.gatherUsageStats false
pause
