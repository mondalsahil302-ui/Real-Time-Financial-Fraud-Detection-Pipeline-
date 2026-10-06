@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python virtual environment not found: "%PYTHON%"
    exit /b 1
)
if not exist "frontend\package.json" (
    echo Frontend package.json not found.
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo Frontend dependencies are missing. Install them in frontend first.
    exit /b 1
)
if not exist "frontend\node_modules\vite\bin\vite.js" (
    echo The project's local Vite executable was not found.
    exit /b 1
)
where.exe node.exe >nul 2>&1
if errorlevel 1 (
    echo node.exe was not found. Install or add the project's Node.js installation to PATH.
    exit /b 1
)
where.exe docker.exe >nul 2>&1
if errorlevel 1 (
    echo Docker CLI was not found.
    exit /b 1
)

echo === Starting Docker infrastructure ===
docker compose up -d
if errorlevel 1 (
    echo docker compose up -d failed.
    exit /b 1
)
call :delay 5
call :waitport 9092 Kafka 120 || exit /b 1
call :waitport 9042 Cassandra 240 || exit /b 1
call :waitport 9090 Prometheus 120 || exit /b 1
call :waitport 3000 Grafana 120 || exit /b 1
call :waitport 9093 Alertmanager 120 || exit /b 1
call :waitport 8080 cAdvisor 120 || exit /b 1

echo.
echo === Starting FastAPI Control Center ===
call :httpup http://localhost:8001/api/health
if not errorlevel 1 (
    echo FastAPI is already healthy on port 8001.
) else (
    call :portup 8001
    if not errorlevel 1 (
        echo Port 8001 is occupied, but the FastAPI health endpoint is unavailable.
        exit /b 1
    )
    start "FraudPipeline-Backend" /min /D "%PROJECT_ROOT%" "%ComSpec%" /d /k ""%PYTHON%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001"
    call :waithttp http://localhost:8001/api/health "FastAPI" 60 || exit /b 1
)
call :delay 2

echo.
echo === Starting Spark streaming ===
call :httpup http://localhost:8002/metrics
if not errorlevel 1 (
    echo Spark is already responding on port 8002.
) else (
    call :portup 8002
    if not errorlevel 1 (
        echo Port 8002 is occupied, but the Spark metrics endpoint is unavailable.
        exit /b 1
    )
    start "FraudPipeline-Spark" /min /D "%PROJECT_ROOT%" "%ComSpec%" /d /k ""%PYTHON%" ".\streaming\spark_streaming.py""
    call :waithttp http://localhost:8002/metrics "Spark" 180 || (
        echo Spark did not expose metrics on port 8002; it may have exited during startup.
        exit /b 1
    )
)
call :delay 2

echo.
echo === Starting investigation consumer ===
call :httpup http://localhost:8000/metrics
if not errorlevel 1 (
    echo Investigation consumer is already responding on port 8000.
) else (
    call :portup 8000
    if not errorlevel 1 (
        echo Port 8000 is occupied, but the metrics endpoint is unavailable.
        exit /b 1
    )
    start "FraudPipeline-Investigation" /min /D "%PROJECT_ROOT%" "%ComSpec%" /d /k ""%PYTHON%" -m rag.investigation.kafka_investigation_consumer"
    call :waithttp http://localhost:8000/metrics "Investigation consumer" 120 || exit /b 1
)
call :delay 2

echo.
echo === Starting Control Center frontend ===
call :httpup http://localhost:5173/
if not errorlevel 1 (
    echo Frontend is already responding on port 5173.
) else (
    call :portup 5173
    if not errorlevel 1 (
        echo Port 5173 is occupied, but the frontend is not responding.
        exit /b 1
    )
    start "FraudPipeline-Frontend" /min /D "%PROJECT_ROOT%\frontend" "%ComSpec%" /d /k "node.exe node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173 --strictPort"
    call :waithttp http://localhost:5173/ "Frontend" 60 || exit /b 1
)

echo.
echo === Project services ===
echo Control Center: http://localhost:5173
echo FastAPI:        http://localhost:8001
echo Metrics:        http://localhost:8000/metrics
echo Spark metrics:  http://localhost:8002/metrics
echo Prometheus:     http://localhost:9090
echo Grafana:        http://localhost:3000
echo Alertmanager:   http://localhost:9093
echo cAdvisor:       http://localhost:8080
echo Kafka:          localhost:9092
echo Cassandra:      localhost:9042
exit /b 0

:waitport
set "WAIT_PORT=%~1"
set "WAIT_NAME=%~2"
set /a WAIT_LIMIT=%~3
set /a WAIT_ELAPSED=0
:waitport_loop
call :portup %WAIT_PORT%
if not errorlevel 1 (
    echo PASS: %WAIT_NAME% is listening on port %WAIT_PORT%.
    exit /b 0
)
if %WAIT_ELAPSED% GEQ %WAIT_LIMIT% (
    echo FAIL: %WAIT_NAME% did not open port %WAIT_PORT%.
    exit /b 1
)
call :delay 3
set /a WAIT_ELAPSED+=3
goto waitport_loop

:waithttp
set "WAIT_URL=%~1"
set "WAIT_NAME=%~2"
set /a WAIT_LIMIT=%~3
set /a WAIT_ELAPSED=0
:waithttp_loop
call :httpup "%WAIT_URL%"
if not errorlevel 1 (
    echo PASS: %WAIT_NAME% responded at %WAIT_URL%.
    exit /b 0
)
if %WAIT_ELAPSED% GEQ %WAIT_LIMIT% (
    echo FAIL: %WAIT_NAME% did not respond at %WAIT_URL%.
    exit /b 1
)
call :delay 3
set /a WAIT_ELAPSED+=3
goto waithttp_loop

:portup
netstat -ano -p tcp | findstr /R /C:":%~1 .*LISTENING" >nul
exit /b %ERRORLEVEL%

:httpup
curl.exe -fsS --max-time 3 -o nul "%~1" >nul 2>&1
exit /b %ERRORLEVEL%

:delay
timeout /t %~1 /nobreak >nul 2>&1
set /a PING_COUNT=%~1
ping.exe -n %PING_COUNT% 127.0.0.1 >nul
exit /b 0
