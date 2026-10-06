@echo off
setlocal
cd /d "%~dp0.."
echo === Container status ===
docker compose ps prometheus grafana alertmanager cadvisor
echo === Listening ports 8000, 9090, 9093, 3000 ===
netstat -ano | findstr LISTENING | findstr ":8000 :9090 :9093 :3000"
echo === Application metrics and health ===
curl.exe -sS --max-time 3 http://localhost:8000/health
curl.exe -sS --max-time 3 http://localhost:8000/readiness
curl.exe -sS --max-time 3 http://localhost:8000/metrics | findstr /c:"fraud_pipeline_events_total"
echo === Prometheus, Grafana, Alertmanager health ===
curl.exe -sS --max-time 5 http://localhost:9090/-/healthy
curl.exe -sS --max-time 5 http://localhost:3000/api/health
curl.exe -sS --max-time 5 http://localhost:9093/-/healthy
echo === Prometheus targets ===
curl.exe -sS --max-time 5 http://localhost:9090/api/v1/targets | findstr /c:"fraud-pipeline-app" /c:"health"
