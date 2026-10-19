@echo off
REM Double-cliquez sur ce fichier pour lancer SAP PM Analyst (Windows)
cd /d "%~dp0"
if not exist .venv (
  echo Installation (premiere utilisation, 1-2 minutes)...
  python -m venv .venv || (echo Python 3.10+ est requis : https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
pause
