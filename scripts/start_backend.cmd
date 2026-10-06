@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
curl.exe -fsS --max-time 3 -o nul http://localhost:8001/api/health >nul 2>&1
if not errorlevel 1 (
  echo Control Center API is already healthy on port 8001.
  exit /b 0
)
netstat -ano -p tcp | findstr /R /C:":8001 .*LISTENING" >nul
if not errorlevel 1 (
  echo Port 8001 is occupied, but the Control Center API is not healthy.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found at .venv. Create it and install backend\requirements.txt first.
  exit /b 1
)
start "FraudPipeline-Backend" /min /D "%CD%" "%ComSpec%" /d /k ""%PYTHON%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001"
call :waithttp 30
if errorlevel 1 (
  echo Control Center API did not become healthy on port 8001.
  exit /b 1
)
echo Control Center API is healthy at http://localhost:8001
exit /b 0

:waithttp
set /a WAIT_SECONDS=%~1
:wait_loop
curl.exe -fsS --max-time 3 -o nul http://localhost:8001/api/health >nul 2>&1
if not errorlevel 1 exit /b 0
if %WAIT_SECONDS% LEQ 0 exit /b 1
timeout /t 2 /nobreak >nul
set /a WAIT_SECONDS-=2
goto wait_loop
