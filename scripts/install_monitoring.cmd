@echo off
setlocal
cd /d "%~dp0.."

if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
  echo This monitoring stack requires Windows AMD64.
  exit /b 1
)
where docker.exe >nul 2>nul || (echo Docker Desktop CLI is required.& exit /b 1)
docker compose version >nul 2>nul || (echo Docker Compose v2 is required.& exit /b 1)
docker info >nul 2>nul || (echo Docker Desktop is not running or is inaccessible.& exit /b 1)
docker compose config --quiet || (echo docker-compose.yml is invalid.& exit /b 1)

echo Pulling the configured monitoring images, including Prometheus 3.15.0 and Grafana OSS 13.2.3...
docker compose pull prometheus grafana alertmanager cadvisor || exit /b 1
docker compose up -d prometheus grafana alertmanager cadvisor || exit /b 1
call "%~dp0validate_monitoring.cmd" --quick
exit /b %ERRORLEVEL%
