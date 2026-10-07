#!/usr/bin/env bash
# Starts the API on http://localhost:8000 (creates the virtual environment on first run).
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Creating the Python virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "Installing / checking Python packages..."
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
exec uvicorn app.main:app --reload --port 8000
