@echo off
setlocal
cd /d "%~dp0.."

echo === Project port status ===
for %%P in (5173 8001 8000 8002 9090 3000 9093 8080 9092 9042) do call :checkport %%P

echo.
echo === HTTP health checks ===
call :checkhttp 5173 http://localhost:5173/
call :checkhttp 8001 http://localhost:8001/api/health
call :checkhttp 8000 http://localhost:8000/metrics
call :checkhttp 8002 http://localhost:8002/metrics
call :checkhttp 9090 http://localhost:9090/-/healthy
call :checkhttp 3000 http://localhost:3000/api/health
call :checkhttp 9093 http://localhost:9093/-/healthy
call :checkhttp 8080 http://localhost:8080/metrics
call :checkhttp 8001 http://localhost:8001/api/llm/status

exit /b 0

:checkport
set "FOUND_PORT=0"
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%~1 .*LISTENING"') do (
    set "FOUND_PORT=1"
    call :showprocess %%P
)
if "%FOUND_PORT%"=="0" echo Port %~1: DOWN
if "%FOUND_PORT%"=="1" echo Port %~1: LISTENING
exit /b 0

:showprocess
tasklist /FI "PID eq %~1" /FO LIST | findstr /I /C:"Image Name:" /C:"PID:"
exit /b 0

:checkhttp
curl.exe -fsS --max-time 4 -o nul "%~2" >nul 2>&1
if errorlevel 1 (
    echo HTTP %~1: DOWN - %~2
) else (
    echo HTTP %~1: UP - %~2
)
exit /b 0
