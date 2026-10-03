"""Persist low-risk Kafka events into the transactions table."""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.cassandra_connection import PROJECT_ROOT, get_cassandra_config
from database.consumer_common import parse_event_time, required_payload_fields, run_consumer, utc_now

load_dotenv(PROJECT_ROOT / ".env")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "transaction_id",
    "event_time",
    "type",
    "nameOrig",
    "nameDest",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "anomaly_score",
    "risk_level",
    "risk_action",
    "final_prediction",
    "final_decision_path",
    "model_version",
    "source",
)

INSERT_CQL = f"""INSERT INTO {get_cassandra_config().keyspace}.transactions (
    name_orig, event_time, transaction_id, event_date, event_hour,
    transaction_type, name_dest, amount, old_balance_orig, new_balance_orig,
    old_balance_dest, new_balance_dest, anomaly_score, risk_level, risk_action,
    xgboost_probability, xgboost_prediction, final_prediction,
    final_decision_path, model_version, source, inserted_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def _optional_float(payload: Mapping[str, Any], name: str) -> float | None:
    value = payload.get(name)
    return None if value is None else float(value)


def _optional_bool(payload: Mapping[str, Any], name: str) -> bool | None:
    value = payload.get(name)
    return None if value is None else bool(int(value))


def build_row(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    """Map the actual Spark low-risk JSON fields to Cassandra columns."""
    required_payload_fields(payload, REQUIRED_FIELDS)
    event_time = parse_event_time(payload["event_time"])
    return (
        str(payload["nameOrig"]),
        event_time,
        str(payload["transaction_id"]),
        date(event_time.year, event_time.month, event_time.day),
        event_time.hour,
        str(payload["type"]),
        str(payload["nameDest"]),
        float(payload["amount"]),
        float(payload["oldbalanceOrg"]),
        float(payload["newbalanceOrig"]),
        float(payload["oldbalanceDest"]),
        float(payload["newbalanceDest"]),
        float(payload["anomaly_score"]),
        str(payload["risk_level"]),
        str(payload["risk_action"]),
        _optional_float(payload, "xgboost_probability"),
        _optional_bool(payload, "xgboost_prediction"),
        bool(int(payload["final_prediction"])),
        str(payload["final_decision_path"]),
        str(payload["model_version"]),
        str(payload["source"]),
        utc_now(),
    )


def main() -> None:
    run_consumer(
        topic=os.environ["LOW_RISK_TOPIC"],
        group_id=os.environ["CASSANDRA_TRANSACTION_CONSUMER_GROUP"],
        insert_cql=INSERT_CQL,
        required_fields=REQUIRED_FIELDS,
        row_builder=build_row,
        service_name="transaction-cassandra-consumer",
    )


if __name__ == "__main__":
    main()
