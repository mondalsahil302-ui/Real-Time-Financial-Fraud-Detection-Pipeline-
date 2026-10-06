"""Verify provisioned observability services and configuration."""
from __future__ import annotations

import json
import base64
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv


def get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def main() -> int:
    load_dotenv(ROOT / ".env")
    base = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
    checks = {}
    try:
        targets = get(base + "/api/v1/targets")["data"]["activeTargets"]
        checks["Prometheus targets configured"] = len(targets) >= 2
        names = get(base + "/api/v1/label/__name__/values")["data"]
        checks["application metric endpoint scraped"] = any(x.startswith("fraud_pipeline_events_total") for x in names)
        rules = get(base + "/api/v1/rules")["data"]["groups"]
        checks["alert and recording rules loaded"] = any(group.get("rules") for group in rules)
        grafana = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
        checks["Grafana reachable"] = get(grafana + "/api/health").get("database") == "ok"
        username = os.getenv("GRAFANA_ADMIN_USER", "admin")
        password = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
        auth = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        headers = {"Authorization": auth}
        checks["Grafana datasource provisioned"] = get(grafana + "/api/datasources/uid/prometheus", headers).get("type") == "prometheus"
        checks["Grafana dashboard provisioned"] = get(grafana + "/api/dashboards/uid/fraud-pipeline", headers).get("dashboard", {}).get("uid") == "fraud-pipeline"
        checks["Grafana provisioning present"] = (ROOT / "monitoring/grafana/provisioning/datasources/prometheus.yml").exists() and (ROOT / "monitoring/grafana/dashboards/fraud-pipeline.json").exists()
        alertmanager = os.getenv("ALERTMANAGER_URL", "http://localhost:9093").rstrip("/")
        with urllib.request.urlopen(alertmanager + "/-/healthy", timeout=5):
            checks["Alertmanager reachable"] = True
    except (OSError, urllib.error.URLError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Observability check could not reach a service ({type(exc).__name__}). Start Docker infrastructure and retry.")
    for name, ok in checks.items(): print(f"{name}: {'OK' if ok else 'FAIL'}")
    expected = ("Prometheus targets configured", "application metric endpoint scraped", "alert and recording rules loaded", "Grafana reachable", "Grafana datasource provisioned", "Grafana dashboard provisioned", "Alertmanager reachable")
    return 0 if all(checks.get(key, False) for key in expected) else 1


if __name__ == "__main__": raise SystemExit(main())
