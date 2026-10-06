@echo off
setlocal
cd /d "%~dp0.."
set QUICK=0
if /i "%~1"=="--quick" set QUICK=1
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")

echo === Validate Prometheus configuration and rules ===
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml || exit /b 1
docker compose exec -T prometheus promtool check rules /etc/prometheus/rules/pipeline.yml || exit /b 1
echo === Validate provisioned dashboards and datasource files ===
"%PYTHON%" -c "import json,pathlib; root=pathlib.Path('monitoring/grafana'); [json.loads(p.read_text(encoding='utf-8')) for p in (root/'dashboards').glob('*.json')]; assert (root/'provisioning/datasources/prometheus.yml').is_file(); assert len(list((root/'dashboards').glob('*.json'))) >= 6; print('Grafana provisioning JSON is valid')" || exit /b 1
echo === HTTP endpoints ===
curl.exe -fsS --max-time 5 http://localhost:9090/-/healthy || exit /b 1
curl.exe -fsS --max-time 5 http://localhost:3000/api/health || exit /b 1
curl.exe -fsS --max-time 5 http://localhost:9093/-/healthy || exit /b 1
curl.exe -fsS --max-time 5 http://localhost:9090/api/v1/targets | findstr /c:"fraud-pipeline-app" >nul || (echo Prometheus fraud-pipeline-app target is missing.& exit /b 1)
curl.exe -fsS --max-time 5 http://localhost:8000/metrics | findstr /c:"fraud_pipeline_events_total" >nul
if errorlevel 1 (echo App metrics are not reachable on port 8000 yet; start the investigation consumer. This is not a Prometheus configuration failure.) else (echo Application metrics endpoint is reachable.)
if "%QUICK%"=="1" exit /b 0
echo === Repository tests and compile checks ===
"%PYTHON%" -m pytest tests/ || exit /b 1
"%PYTHON%" -m py_compile producer\producer.py || exit /b 1
"%PYTHON%" -m py_compile streaming\spark_streaming.py || exit /b 1
