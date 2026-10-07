#!/usr/bin/env bash
# Starts the React app on http://localhost:5173 (installs packages on first run).
set -e
cd "$(dirname "$0")"
[ -d node_modules ] || npm install
exec npm run dev
