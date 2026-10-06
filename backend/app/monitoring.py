from __future__ import annotations

import os
import math
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import config

PROM_QUERIES = {
    "transactions_per_second": ("sum(rate(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"}[5m]))", "tx/s", "Spark processed transaction rate"),
    "transactions_processed": ("sum(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"})", "transactions", "Spark processed transactions observed by Prometheus"),
    "fraud_alerts": ("sum(fraud_pipeline_events_total{component=\"spark\",event=\"fraud_alerts_produced\"})", "alerts", "Fraud alerts produced by Spark"),
    "low_risk": ("sum(fraud_pipeline_events_total{component=\"spark\",event=\"low_risk_produced\"})", "transactions", "Low-risk decisions produced by Spark"),
    "investigations_completed": ("sum(fraud_pipeline_events_total{component=\"investigation\",event=\"completed\",status=~\"completed|partial|insufficient_evidence\"})", "investigations", "Completed or partial investigation outcomes"),
    "investigations_failed": ("sum(fraud_pipeline_events_total{component=\"investigation\",event=\"completed\",status=\"failed\"})", "investigations", "Failed investigation outcomes"),
    "detection_latency_p95": ("histogram_quantile(0.95,sum by(le)(rate(fraud_pipeline_duration_seconds_bucket{component=\"spark\"}[5m])))", "seconds", "Spark micro-batch duration p95; per-transaction latency is not instrumented"),
    "investigation_latency_p95": ("histogram_quantile(0.95,sum by(le)(rate(fraud_pipeline_duration_seconds_bucket{component=\"investigation\"}[5m])))", "seconds", "Investigation duration p95"),
    "rag_latency_p95": ("histogram_quantile(0.95,sum by(le)(rate(fraud_pipeline_duration_seconds_bucket{component=\"rag\"}[5m])))", "seconds", "RAG retrieval duration p95"),
    "llm_requests": ("sum(fraud_pipeline_events_total{component=\"llm\",event=\"generation\"})", "requests", "LLM generation attempts"),
    "kafka_errors": ("sum(fraud_pipeline_events_total{component=\"kafka\",status=\"failure\"})", "errors", "Instrumented Kafka operation failures"),
    "cassandra_writes": ("sum(fraud_pipeline_events_total{component=\"cassandra\",event=\"write\",status=\"success\"})", "writes", "Successful application Cassandra writes"),
    "cassandra_failures": ("sum(fraud_pipeline_events_total{component=\"cassandra\",status=\"failure\"})", "errors", "Instrumented Cassandra failures"),
    "app_availability": ("avg(up{job=~\"fraud-pipeline-app|spark-streaming|transaction-producer\"})", "ratio", "Availability across configured host application targets"),
    "container_cpu": ("sum by(name)(rate(container_cpu_usage_seconds_total[5m]))", "cores", "Container CPU where cAdvisor exposes it"),
    "container_memory": ("sum by(name)(container_memory_usage_bytes)", "bytes", "Container memory where cAdvisor exposes it"),
}


def _http_health(url: str, path: str, *, timeout: float = 1.5, auth=None) -> dict:
    try:
        response = httpx.get(f"{url}{path}", timeout=timeout, auth=auth)
        response.raise_for_status()
        return {"status": "healthy", "available": True, "checked_at": time.time()}
    except Exception as exc:
        return {"status": "unavailable", "available": False, "detail": type(exc).__name__, "checked_at": time.time()}


def prometheus_health() -> dict:
    return _http_health(config.PROMETHEUS_URL, "/-/healthy")


def grafana_health() -> dict:
    return _http_health(config.GRAFANA_URL, "/api/health")


def alertmanager_health() -> dict:
    return _http_health(config.ALERTMANAGER_URL, "/-/healthy")


def _prom_query(expression: str, timeout: float = 2.0) -> list[dict]:
    response = httpx.get(f"{config.PROMETHEUS_URL}/api/v1/query", params={"query": expression}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "success":
        raise RuntimeError("Prometheus query did not succeed")
    return [{"labels": row.get("metric", {}), "value": _json_number(row["value"][1])}
            for row in body.get("data", {}).get("result", [])]


def _json_number(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def metric(name: str) -> dict:
    expression, unit, description = PROM_QUERIES[name]
    try:
        values = _prom_query(expression)
        return {"name": name, "expression": expression, "unit": unit, "description": description,
                "available": bool(values), "values": values}
    except Exception as exc:
        return {"name": name, "expression": expression, "unit": unit, "description": description,
                "available": False, "values": [], "error": type(exc).__name__}


def metrics_overview() -> dict:
    health = prometheus_health()
    return {"prometheus": health, "metrics": {name: metric(name) for name in PROM_QUERIES}}


def prometheus_targets() -> dict:
    try:
        response = httpx.get(f"{config.PROMETHEUS_URL}/api/v1/targets", timeout=2)
        response.raise_for_status()
        body = response.json()
        targets = [{"job": target.get("labels", {}).get("job", "unknown"),
                    "instance": target.get("labels", {}).get("instance", "unknown"),
                    "health": target.get("health", "unknown"),
                    "last_scrape": target.get("lastScrape"),
                    "scrape_duration_seconds": target.get("lastScrapeDuration"),
                    "last_error": target.get("lastError") or None}
                   for target in body.get("data", {}).get("activeTargets", [])]
        return {"available": True, "targets": targets}
    except Exception as exc:
        return {"available": False, "targets": [], "error": type(exc).__name__}


def grafana_dashboards() -> dict:
    user = os.getenv("GRAFANA_ADMIN_USER", "admin")
    password = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
    try:
        response = httpx.get(f"{config.GRAFANA_URL}/api/search", params={"type": "dash-db"},
                             auth=(user, password), timeout=2)
        response.raise_for_status()
        items = response.json()
        return {"available": True, "dashboards": [{"title": item["title"], "uid": item["uid"],
                "url": item["url"]} for item in items if item.get("uid") and item.get("url")]}
    except Exception as exc:
        return {"available": False, "dashboards": [], "error": type(exc).__name__}


def _tcp(host: str, port: int, timeout: float = 0.6) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"status": "healthy", "available": True}
    except OSError as exc:
        return {"status": "unavailable", "available": False, "detail": type(exc).__name__}


def _kafka_status() -> dict:
    address = config.KAFKA_SERVERS.split(",", 1)[0].strip()
    host, _, port_text = address.rpartition(":")
    return _tcp(host.strip("[]") or "localhost", int(port_text or "9092"))


def _cassandra_status() -> dict:
    try:
        from database.cassandra_connection import close_connection, get_session
        cluster, session = get_session()
        try:
            row = session.execute("SELECT release_version FROM system.local", timeout=2).one()
            if not row:
                raise RuntimeError("Cassandra returned no local node")
            return {"status": "healthy", "available": True, "version": row.release_version}
        finally:
            close_connection(cluster, session)
    except Exception as exc:
        return {"status": "unavailable", "available": False, "detail": type(exc).__name__}


def _chroma_status() -> dict:
    raw = Path(os.getenv("VECTOR_DB_PATH", "./vector_db")).expanduser()
    path = raw if raw.is_absolute() else config.PROJECT_ROOT / raw
    if not path.is_dir():
        return {"status": "unavailable", "available": False}
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(path))
        collections = {item.name for item in client.list_collections()}
        required = {os.getenv("CHROMA_KNOWLEDGE_COLLECTION", "fraud_knowledge"),
                    os.getenv("CHROMA_PAYSIM_COLLECTION", "paysim_cases")}
        missing = sorted(required - collections)
        return {"status": "ready" if not missing else "collections unavailable", "available": not missing,
                "collections": sorted(required - set(missing)), "missing_collections": missing}
    except Exception as exc:
        return {"status": "unavailable", "available": False, "detail": type(exc).__name__}


_last_gemini_check = 0.0
_last_gemini_result = None


def _gemini_status() -> dict:
    global _last_gemini_check, _last_gemini_result
    now = time.time()
    if _last_gemini_result is not None and (now - _last_gemini_check) < 60:
        return _last_gemini_result
    try:
        from rag.investigation.llm_provider import verify_configured_chat_provider
        _last_gemini_result = verify_configured_chat_provider()
    except Exception as exc:
        _last_gemini_result = {"status": "unavailable", "available": False, "detail": str(exc)}
    _last_gemini_check = now
    return _last_gemini_result


@lru_cache(maxsize=1)
def _spark_target_cached():
    return prometheus_targets()


def system_status(api_available: bool = True) -> dict:
    targets_result = prometheus_targets()
    target_by_job = {item["job"]: item for item in targets_result["targets"]}
    prometheus = prometheus_health()
    grafana = grafana_health()
    alertmanager = alertmanager_health()
    checks = {
        "kafka": _kafka_status(),
        "spark": ({"status": "running", "available": True} if target_by_job.get("spark-streaming", {}).get("health") == "up"
                  else {"status": "unavailable", "available": False, "detail": "Prometheus spark-streaming target is not UP"}),
        "cassandra": _cassandra_status(),
        "chroma": _chroma_status(),
        "gemini": _gemini_status(),
        "fraud_api": {"status": "healthy" if api_available else "unavailable", "available": api_available},
        "prometheus": prometheus,
        "grafana": grafana,
        "alertmanager": alertmanager,
        "cadvisor": ({"status": "healthy" if target_by_job.get("cadvisor", {}).get("health") == "up" else "unavailable",
                       "available": target_by_job.get("cadvisor", {}).get("health") == "up"}),
    }
    return {"checked_at": time.time(), "services": checks, "prometheus_targets": targets_result}
