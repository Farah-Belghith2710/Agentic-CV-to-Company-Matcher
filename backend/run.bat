@echo off
rem Starts the API on http://localhost:8000 (creates the virtual environment on first run).
cd /d "%~dp0"
if not exist .venv (
  echo Creating the Python virtual environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing / checking Python packages...
python -m pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
uvicorn app.main:app --reload --port 8000
pause
