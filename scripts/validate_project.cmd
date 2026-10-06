@echo off
setlocal
cd /d "%~dp0.."
set "FAIL=0"

echo === Frontend ===
call :checkhttp "http://localhost:5173/"

echo.
echo === FastAPI Control Center ===
call :checkhttp "http://localhost:8001/api/health"
call :checkhttp "http://localhost:8001/api/llm/status"
call :checkhttp "http://localhost:8001/api/system/status"
call :checkhttp "http://localhost:8001/api/monitoring/overview"

echo.
echo === Application metrics ===
call :checkhttp "http://localhost:8000/metrics"

echo.
echo === Spark metrics ===
call :checkhttp "http://localhost:8002/metrics"

echo.
echo === Monitoring services ===
call :checkhttp "http://localhost:9090/-/healthy"
call :checkhttp "http://localhost:3000/"
call :checkhttp "http://localhost:9093/-/healthy"
call :checkhttp "http://localhost:8080/metrics"

echo.
echo === Kafka and Cassandra ports ===
call :checkport 9092 Kafka
call :checkport 9042 Cassandra

if "%FAIL%"=="1" (
    echo.
    echo One or more required services are unavailable.
    exit /b 1
)
echo.
echo All required service checks passed.
exit /b 0

:checkhttp
curl.exe -fsS --max-time 8 -o nul "%~1" >nul 2>&1
if errorlevel 1 (
    echo FAIL: %~1
    set "FAIL=1"
) else (
    echo PASS: %~1
)
exit /b 0

:checkport
netstat -ano -p tcp | findstr /R /C:":%~1 .*LISTENING" >nul
if errorlevel 1 (
    echo FAIL: %~2 is not listening on port %~1.
    set "FAIL=1"
) else (
    echo PASS: %~2 is listening on port %~1.
)
exit /b 0
