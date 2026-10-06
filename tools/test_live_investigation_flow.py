"""Explicitly publish one marked synthetic alert to the configured fraud-alerts topic."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv


def main():
    load_dotenv(ROOT / ".env")
    from kafka import KafkaProducer
    topic = os.getenv("FRAUD_ALERTS_TOPIC")
    if not topic: raise SystemExit("FRAUD_ALERTS_TOPIC is not configured")
    txn = "RAG_TEST_TXN_" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    alert = {"transaction_id": txn, "alert_id": "rag_test_" + txn, "event_time": now, "type": "TRANSFER",
        "nameOrig": "RAG_TEST_ACCOUNT_ORIGIN", "nameDest": "RAG_TEST_ACCOUNT_DESTINATION", "amount": 2500.0,
        "oldbalanceOrg": 3000.0, "newbalanceOrig": 500.0, "oldbalanceDest": 0.0, "newbalanceDest": 2500.0,
        "anomaly_score": 0.91, "risk_level": "HIGH", "risk_action": "ALERT", "alert_required": True,
        "xgboost_probability": 0.82, "xgboost_prediction": True, "final_prediction": True,
        "final_decision_path": "RAG_TEST_SYNTHETIC", "final_risk_action": "REVIEW", "model_version": "rag-test",
        "source": "rag_test", "status": "NEW"}
    producer = KafkaProducer(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(","),
        value_serializer=lambda value: json.dumps(value).encode("utf-8"))
    try:
        metadata = producer.send(topic, alert).get(timeout=15)
        print(f"Published marked synthetic alert_id={alert['alert_id']} topic={metadata.topic} partition={metadata.partition} offset={metadata.offset}")
    finally: producer.close()


if __name__ == "__main__": main()
