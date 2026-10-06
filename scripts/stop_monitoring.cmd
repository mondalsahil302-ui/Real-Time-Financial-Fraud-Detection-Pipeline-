@echo off
setlocal
cd /d "%~dp0.."
where docker.exe >nul 2>nul || (echo Docker Desktop CLI is required.& exit /b 1)
docker compose stop prometheus grafana alertmanager cadvisor
if errorlevel 1 exit /b %ERRORLEVEL%
echo Stopped Prometheus, Grafana, Alertmanager, and cAdvisor. Kafka and Cassandra were left running.
