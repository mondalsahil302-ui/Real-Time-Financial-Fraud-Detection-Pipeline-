"""Process one fraud alert into a durable retrieval-only context artifact."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from rag import config
from rag.retrieval.orchestrator import RetrievalOrchestrator

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _default_orchestrator():
    """Reuse retrieval adapters and their cached model/session across alerts."""
    return RetrievalOrchestrator()


def _artifact_name(alert_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(alert_id)).strip("._")
    return safe[:120] or "alert"


def save_context(context: dict, output_dir: Path | None = None) -> Path:
    destination = Path(output_dir or (config.OUTPUT_PATH / "investigations"))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{_artifact_name(context['alert']['alert_id'])}.json"
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def process_alert(alert: dict, orchestrator=None, output_dir: Path | None = None) -> dict:
    """Normalize, retrieve, rank, build and save a context; never invoke an LLM."""
    context = (orchestrator or _default_orchestrator()).process(alert)
    artifact = save_context(context, output_dir)
    context["artifact_path"] = str(artifact)
    LOGGER.info("Saved investigation context alert_id=%s path=%s", context["alert"].get("alert_id"), artifact)
    return context


def consume_kafka(topic: str | None = None, bootstrap_servers: str | None = None) -> None:
    """Consume the existing fraud-alert topic and commit after context is saved."""
    load_dotenv(config.PROJECT_ROOT / ".env")
    topic = topic or os.getenv("FRAUD_ALERTS_TOPIC")
    bootstrap_servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    if not topic:
        raise ValueError("Set FRAUD_ALERTS_TOPIC or pass --topic before consuming alerts")
    from kafka import KafkaConsumer
    consumer = KafkaConsumer(topic, bootstrap_servers=bootstrap_servers.split(","),
                             group_id=config.RAG_KAFKA_CONSUMER_GROUP, enable_auto_commit=False,
                             auto_offset_reset="latest", value_deserializer=lambda data: json.loads(data.decode("utf-8")))
    LOGGER.info("Listening for fraud alerts on topic=%s", topic)
    try:
        for message in consumer:
            process_alert(message.value)
            consumer.commit()
    finally:
        consumer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert-json", help="Path to one JSON alert file for one-shot processing")
    parser.add_argument("--consume-kafka", action="store_true", help="Consume FRAUD_ALERTS_TOPIC continuously")
    parser.add_argument("--topic")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.consume_kafka:
        consume_kafka(topic=args.topic)
        return
    if not args.alert_json:
        parser.error("provide --alert-json PATH or --consume-kafka")
    alert = json.loads(Path(args.alert_json).read_text(encoding="utf-8"))
    context = process_alert(alert)
    print(json.dumps({"alert_id": context["alert"]["alert_id"], "artifact_path": context["artifact_path"],
                      "retrieval_status": context["retrieval_status"], "evidence_summary": context["evidence_summary"]}, indent=2))


if __name__ == "__main__":
    main()
