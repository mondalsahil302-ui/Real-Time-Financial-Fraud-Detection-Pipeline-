"""Low-cardinality Prometheus metrics and lightweight app health endpoints."""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

LOGGER = logging.getLogger(__name__)
REQUESTS = Counter("fraud_pipeline_events_total", "Pipeline events", ("component", "event", "status"))
DURATION = Histogram("fraud_pipeline_duration_seconds", "Pipeline operation duration", ("component", "operation"))
LLM_REQUESTS = Counter("llm_requests_total", "Ask AI provider requests", ("provider", "status", "operation"))
LLM_SUCCESSES = Counter("llm_success_total", "Successful Ask AI provider responses", ("provider", "status", "operation"))
LLM_FAILURES = Counter("llm_failure_total", "Failed Ask AI provider responses", ("provider", "status", "operation"))
LLM_LATENCY = Histogram("llm_latency_seconds", "Ask AI provider request latency", ("provider", "status", "operation"))
_SERVER = None
_SERVERS: dict[int, ThreadingHTTPServer] = {}

# Publish zero-valued known series so a freshly started process can be scraped
# and monitored before its first transaction. Labels remain fixed-cardinality.
for _component, _event, _status in (
    ("llm", "generation", "success"), ("llm", "generation", "failure"), ("llm", "generation", "invalid_response"),
    ("llm", "generation", "timeout"),
    ("kafka", "transaction_produced", "success"), ("kafka", "transaction_produced", "failure"),
    ("kafka", "dead_letter", "success"), ("kafka", "dead_letter", "failure"),
    ("investigation", "completed", "completed"), ("investigation", "completed", "partial"),
    ("investigation", "completed", "insufficient_evidence"), ("investigation", "completed", "failed"),
    ("rag", "retrieval", "success"), ("rag", "retrieval", "failure"), ("rag", "retrieval", "partial"),
    ("cassandra", "retrieval", "failure"), ("cassandra", "write", "success"), ("cassandra", "write", "failure"),
    ("kafka", "consume", "failure"), ("kafka", "produce", "failure"),
):
    REQUESTS.labels(_component, _event, _status).inc(0)


def count(component: str, event: str, status: str = "success", amount: float = 1.0) -> None:
    REQUESTS.labels(component, event, status).inc(amount)


def _tcp_ready(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _readiness_checks() -> dict[str, bool]:
    """Check dependency sockets and local Chroma storage without doing model work."""
    kafka_endpoint = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",", 1)[0].strip()
    kafka_host, _, kafka_port = kafka_endpoint.rpartition(":")
    kafka_host = kafka_host.strip("[]") or "localhost"
    try:
        kafka_port_number = int(kafka_port or "9092")
    except ValueError:
        kafka_port_number = 9092

    cassandra_host = os.getenv("CASSANDRA_HOST", "localhost")
    try:
        cassandra_port = int(os.getenv("CASSANDRA_PORT", "9042"))
    except ValueError:
        cassandra_port = 9042

    vector_path = Path(os.getenv("VECTOR_DB_PATH", "./vector_db")).expanduser()
    if not vector_path.is_absolute():
        vector_path = Path(__file__).resolve().parents[1] / vector_path

    return {
        "kafka": _tcp_ready(kafka_host, kafka_port_number),
        "cassandra": _tcp_ready(cassandra_host, cassandra_port),
        "chroma": vector_path.is_dir(),
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            data, content_type, code = generate_latest(), CONTENT_TYPE_LATEST, 200
        elif self.path == "/health":
            data, content_type, code = json.dumps({"status": "ok"}).encode(), "application/json", 200
        elif self.path == "/readiness":
            dependencies = _readiness_checks()
            ready = all(dependencies.values())
            data = json.dumps({"status": "ok" if ready else "not_ready", "dependencies": dependencies}).encode()
            content_type, code = "application/json", 200 if ready else 503
        else:
            data, content_type, code = b"not found", "text/plain", 404
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        LOGGER.debug("metrics endpoint %s", self.path)


def start_metrics_server(host: str | None = None, port: int | None = None):
    global _SERVER
    host = host or os.getenv("METRICS_HOST", "0.0.0.0")
    port = int(port or os.getenv("METRICS_PORT", "8000"))
    if port in _SERVERS:
        return _SERVERS[port]
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
        _SERVERS[port] = server
        if _SERVER is None:
            _SERVER = server
        threading.Thread(target=server.serve_forever, name=f"prometheus-metrics-{port}", daemon=True).start()
        LOGGER.info("Application metrics endpoint listening port=%s", port)
        return server
    except OSError as exc:
        LOGGER.warning("Metrics server port %s already bound or unavailable: %s", port, exc)
        return _SERVERS.get(port)
