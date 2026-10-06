from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def setting(name: str, default: str) -> str:
    return os.getenv(name, default)


def sqlite_path() -> Path:
    raw = Path(setting("CONTROL_CENTER_DB", "backend/data/control_center.sqlite3")).expanduser()
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


API_HOST = setting("BACKEND_HOST", "127.0.0.1")
API_PORT = int(setting("BACKEND_PORT", "8001"))
FRONTEND_ORIGIN = setting("FRONTEND_ORIGIN", "http://localhost:5173")
FRONTEND_ORIGINS = list(dict.fromkeys([FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"]))
PROMETHEUS_URL = setting("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
GRAFANA_URL = setting("GRAFANA_URL", "http://localhost:3000").rstrip("/")
ALERTMANAGER_URL = setting("ALERTMANAGER_URL", "http://localhost:9093").rstrip("/")
KAFKA_SERVERS = setting("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
FRAUD_ALERTS_TOPIC = setting("FRAUD_ALERTS_TOPIC", "fraud-alerts")
LOW_RISK_TOPIC = setting("LOW_RISK_TOPIC", "low-risk-transactions")
