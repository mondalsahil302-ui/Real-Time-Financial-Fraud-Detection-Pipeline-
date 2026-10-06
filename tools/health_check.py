"""Report local dependency health without logging credentials."""
from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv


def _http(url: str, timeout=3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def _tcp(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def main() -> int:
    load_dotenv(ROOT / ".env")
    kafka = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")[0]
    kh, kp = kafka.rsplit(":", 1)
    cassandra_host = os.getenv("CASSANDRA_HOST", "localhost")
    cassandra_port = int(os.getenv("CASSANDRA_PORT", "9042"))
    chroma_path = Path(os.getenv("VECTOR_DB_PATH", ROOT / "vector_db"))
    api = os.getenv("CONTROL_CENTER_URL", "http://localhost:8001").rstrip("/")
    services = [
        ("Kafka", _tcp(kh, int(kp))),
        ("Cassandra", _tcp(cassandra_host, cassandra_port)),
        ("Chroma", chroma_path.exists() and any(chroma_path.iterdir())),
        ("Gemini (via API)", _http(api + "/api/llm/status")),
        ("Prometheus", _http(os.getenv("PROMETHEUS_URL", "http://localhost:9090") + "/-/healthy")),
        ("Grafana", _http(os.getenv("GRAFANA_URL", "http://localhost:3000") + "/api/health")),
        ("Alertmanager", _http(os.getenv("ALERTMANAGER_URL", "http://localhost:9093") + "/-/healthy")),
    ]
    print(f"{'SERVICE':<16} STATUS")
    for name, healthy in services:
        print(f"{name:<16} {'OK' if healthy else 'UNAVAILABLE'}")
    return 0 if all(ok for _, ok in services) else 1


if __name__ == "__main__":
    raise SystemExit(main())
