@echo off
setlocal
cd /d "%~dp0.."
where docker.exe >nul 2>nul || (echo Docker Desktop CLI is required.& exit /b 1)
docker info >nul 2>nul || (echo Docker Desktop is not running or is inaccessible.& exit /b 1)
docker compose up -d prometheus grafana alertmanager cadvisor || exit /b 1
ping.exe 127.0.0.1 -n 6 >nul
call "%~dp0status_monitoring.cmd"
