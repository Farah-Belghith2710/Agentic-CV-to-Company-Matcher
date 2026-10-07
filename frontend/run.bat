@echo off
rem Starts the React app on http://localhost:5173 (installs packages on first run).
cd /d "%~dp0"
if not exist node_modules call npm install
call npm run dev
pause
