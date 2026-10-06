@echo off
setlocal EnableExtensions
cd /d "%~dp0..\frontend"
curl.exe -fsS --max-time 3 -o nul http://localhost:5173/ >nul 2>&1
if not errorlevel 1 (
  echo Control Center frontend is already healthy on port 5173.
  exit /b 0
)
netstat -ano -p tcp | findstr /R /C:":5173 .*LISTENING" >nul
if not errorlevel 1 (
  echo Port 5173 is occupied, but the Control Center frontend is not healthy.
  exit /b 1
)
if not exist "node_modules" (
  echo Frontend packages missing. Run npm install in the frontend directory first.
  exit /b 1
)
if not exist "node_modules\vite\bin\vite.js" (
  echo The project's local Vite executable was not found.
  exit /b 1
)
where.exe node.exe >nul 2>&1
if errorlevel 1 (
  echo node.exe was not found on PATH.
  exit /b 1
)
start "FraudPipeline-Frontend" /min /D "%CD%" "%ComSpec%" /d /k "node.exe node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173 --strictPort"
call :waithttp 30
if errorlevel 1 (
  echo Control Center frontend did not become healthy on port 5173.
  exit /b 1
)
echo Control Center frontend is healthy at http://localhost:5173
exit /b 0

:waithttp
set /a WAIT_SECONDS=%~1
:wait_loop
curl.exe -fsS --max-time 3 -o nul http://localhost:5173/ >nul 2>&1
if not errorlevel 1 exit /b 0
if %WAIT_SECONDS% LEQ 0 exit /b 1
timeout /t 2 /nobreak >nul
set /a WAIT_SECONDS-=2
goto wait_loop
