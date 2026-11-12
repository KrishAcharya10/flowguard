@echo off
rem Builds the website (so you never see an old version) and starts FlowGuard on http://127.0.0.1:8000
rem Use:  double-click this file, or run  start-flowguard.cmd  from the project folder.
rem Add the word "reset" to also rebuild the demo data:  start-flowguard.cmd reset
cd /d "%~dp0frontend"
if not exist node_modules call npm install
call npm run build
if errorlevel 1 (echo Frontend build FAILED. Fix the errors above first. & pause & exit /b 1)
cd /d "%~dp0backend"
if /i "%1"=="reset" .venv\Scripts\python -m app.seed.reset
echo.
echo FlowGuard is starting on http://127.0.0.1:8000   (press Ctrl+C to stop)
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
