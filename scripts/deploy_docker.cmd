@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo ============================================================================
echo Real-Time Financial Fraud Detection Platform - Docker Stack Launcher
echo ============================================================================

where.exe docker.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI not found. Please install or start Docker Desktop.
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker daemon is not running. Please start Docker Desktop first.
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env file not found. Creating from .env.example...
        copy .env.example .env >nul
        echo [WARN] Created default .env. Please configure GEMINI_API_KEY in .env before running AI investigations.
    ) else (
        echo [ERROR] Neither .env nor .env.example found!
        exit /b 1
    )
)

echo.
echo [1/3] Building production images (fraud-detection-api:1.0.0, fraud-detection-frontend:1.0.0)...
docker compose build
if errorlevel 1 (
    echo [ERROR] docker compose build failed!
    exit /b 1
)

echo.
echo [2/3] Launching containerized microservice pipeline...
docker compose up -d
if errorlevel 1 (
    echo [ERROR] docker compose up failed!
    exit /b 1
)

echo.
echo [3/3] Waiting for service health...
timeout /t 5 /nobreak >nul
docker compose ps

echo.
echo ============================================================================
echo Stack Successfully Started!
echo ============================================================================
echo Control Center UI:   http://localhost:5173
echo FastAPI & Docs:      http://localhost:8001/docs
echo Grafana Dashboards:  http://localhost:3000 (admin / admin)
echo Prometheus Console:  http://localhost:9090
echo Alertmanager:        http://localhost:9093
echo ============================================================================
echo To stop services safely without data loss, run: docker compose down
echo ============================================================================
exit /b 0

