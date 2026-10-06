"""Live smoke test: synthetic Kafka transaction through Spark and investigation persistence."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv


def main() -> int:
    load_dotenv(ROOT / ".env")
    try:
        from kafka import KafkaConsumer, KafkaProducer
        from database.cassandra_connection import get_session
        from rag.retrieval.normalization import normalize_alert
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        return 1
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")
    input_topic = os.getenv("TRANSACTIONS_TOPIC", "transactions")
    out_topics = [os.getenv("FRAUD_ALERTS_TOPIC", "fraud-alerts"), os.getenv("LOW_RISK_TOPIC", "low-risk-transactions")]
    txid = "PIPELINE_SMOKE_TXN_" + uuid.uuid4().hex[:16]
    account = "PIPELINE_SMOKE_ORIGIN_" + uuid.uuid4().hex[:12]
    event = {"transaction_id": txid, "event_time": datetime.now(timezone.utc).isoformat(), "source": "synthetic_smoke",
        "step": 999999, "event_step": 999999, "type": "TRANSFER", "amount": 950000.0, "nameOrig": account,
        "oldbalanceOrg": 1000000.0, "newbalanceOrig": 50000.0, "nameDest": "PIPELINE_SMOKE_DEST_" + uuid.uuid4().hex[:12],
        "oldbalanceDest": 0.0, "newbalanceDest": 950000.0}
    consumer = None
    try:
        consumer = KafkaConsumer(*out_topics, bootstrap_servers=bootstrap, group_id="pipeline-smoke-" + uuid.uuid4().hex,
            enable_auto_commit=False, auto_offset_reset="latest", value_deserializer=lambda b: json.loads(b.decode("utf-8")))
        producer = KafkaProducer(bootstrap_servers=bootstrap, key_serializer=lambda x: x.encode("utf-8"),
            value_serializer=lambda x: json.dumps(x).encode("utf-8"), acks="all")
        try:
            meta = producer.send(input_topic, key=account, value=event).get(timeout=20)
            producer.flush()
        finally:
            producer.close()
        print(f"Kafka accepted synthetic transaction {txid} at {meta.topic}/{meta.partition}/{meta.offset}")
        routed = None
        routed_topic = None
        deadline = time.time() + int(os.getenv("PIPELINE_SMOKE_TIMEOUT", "120"))
        while time.time() < deadline and routed is None:
            for record in consumer.poll(timeout_ms=1000, max_records=100).values():
                for message in record:
                    payload = message.value
                    if str(payload.get("transaction_id")) == txid:
                        routed = payload
                        routed_topic = message.topic
                        break
        if routed is None:
            raise RuntimeError("Spark did not publish this transaction to either output topic before timeout")
        print(f"Spark routed transaction via risk={routed.get('risk_level')} decision={routed.get('final_decision_path')}")
        if routed_topic == out_topics[0]:
            alert = normalize_alert(routed)
            cluster, session = get_session()
            try:
                statement = session.prepare("SELECT investigation_id, investigation_status FROM fraud_detection.investigation_results WHERE alert_id = ? LIMIT 1")
                deadline = time.time() + int(os.getenv("PIPELINE_SMOKE_INVESTIGATION_TIMEOUT", "180"))
                row = None
                while time.time() < deadline:
                    row = session.execute(statement, (alert["alert_id"],)).one()
                    if row: break
                    time.sleep(2)
                if row is None:
                    raise RuntimeError("Alert reached Kafka but no Cassandra investigation result appeared; verify investigation consumer, Chroma, and Gemini configuration")
                print(f"Investigation persisted: id={row.investigation_id} status={row.investigation_status}")
            finally:
                from database.cassandra_connection import close_connection
                close_connection(cluster, session)
        else:
            print("Output is low-risk; the investigation branch was not expected for this transaction.")
        return 0
    except Exception as exc:
        print(f"Full pipeline smoke test failed ({type(exc).__name__}): {exc}")
        return 1
    finally:
        if consumer is not None: consumer.close()


if __name__ == "__main__": raise SystemExit(main())
