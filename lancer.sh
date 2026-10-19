#!/usr/bin/env bash
# Lance SAP PM Analyst (macOS / Linux) : ./lancer.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Installation (première utilisation, 1-2 minutes)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi
exec .venv/bin/python -m streamlit run app.py
