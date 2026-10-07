#!/usr/bin/env bash
# CV Matcher: one command to start the app at http://localhost:8000
# The first run sets up what is missing (Python packages, web app build).
# After changing the React code, delete frontend/dist so it is rebuilt.
set -e
cd "$(dirname "$0")"
if [ ! -x backend/.venv/bin/python ]; then
  echo "Creating the Python environment..."
  python3 -m venv backend/.venv
fi
if ! backend/.venv/bin/python -c "import langgraph" 2>/dev/null; then
  echo "Installing Python packages, this takes a few minutes the first time..."
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
if [ ! -f frontend/dist/index.html ]; then
  echo "Building the web app..."
  (cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
fi
echo
echo "CV Matcher is starting. Your browser will open http://localhost:8000"
echo "Keep this terminal open while you use the app. Press Ctrl+C to stop."
backend/.venv/bin/python -c "import time, webbrowser; time.sleep(5); webbrowser.open('http://localhost:8000')" &
cd backend
exec .venv/bin/python -m uvicorn app.main:app --port 8000
