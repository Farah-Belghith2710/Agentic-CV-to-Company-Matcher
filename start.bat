@echo off
rem CV Matcher: double-click to start the app at http://localhost:8000
rem The first run sets up what is missing (Python packages, web app build).
rem After changing the React code, delete frontend\dist so it is rebuilt.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating the Python environment...
  py -3.10 -m venv backend\.venv 2>nul || py -3 -m venv backend\.venv 2>nul || python -m venv backend\.venv
)
if not exist "backend\.venv\Lib\site-packages\langgraph" (
  echo Installing Python packages, this takes a few minutes the first time...
  "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
)
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

if not exist "frontend\dist\index.html" (
  echo Building the web app...
  pushd frontend
  if not exist node_modules call npm install
  call npm run build
  popd
)

echo.
echo CV Matcher is starting. Your browser will open http://localhost:8000
echo Keep this window open while you use the app. Close it to stop the app.
echo.
start "" /b "backend\.venv\Scripts\python.exe" -c "import time, webbrowser; time.sleep(5); webbrowser.open('http://localhost:8000')"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
pause
