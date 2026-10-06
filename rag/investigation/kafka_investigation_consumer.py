"""Long-running fraud-alert consumer with persist-before-offset-commit semantics."""
from __future__ import annotations

import json
import logging
import os
import time
import base64
from datetime import datetime, timezone

from dotenv import load_dotenv

from rag import config
from rag.investigation.investigation_service import investigate_alert
from rag.metrics import count

LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_ATTEMPTS = 3


def _decode_alert(value):
    if isinstance(value, bytes):
        value = json.loads(value.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Kafka alert payload must be a JSON object")
    if not value.get("transaction_id") and not value.get("alert_id"):
        raise ValueError("Kafka alert needs transaction_id or alert_id")
    return value


def _send_dead_letter(bootstrap_servers, topic, message, error_code):
    """Durably forward a non-retryable malformed record before committing it."""
    from kafka import KafkaProducer
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError

    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers.split(","), client_id="fraud-investigation-dlq-admin")
    try:
        try:
            admin.create_topics([NewTopic(name=topic, num_partitions=1, replication_factor=1)], validate_only=False)
        except TopicAlreadyExistsError:
            pass
    finally:
        admin.close()
    producer = KafkaProducer(bootstrap_servers=bootstrap_servers.split(","), value_serializer=lambda value: json.dumps(value).encode("utf-8"), acks="all")
    raw = message.value if isinstance(message.value, bytes) else json.dumps(message.value, default=str).encode("utf-8")
    record = {"source_topic": message.topic, "source_partition": message.partition, "source_offset": message.offset,
        "error_code": error_code, "received_at": datetime.now(timezone.utc).isoformat(),
        "raw_value_base64": base64.b64encode(raw).decode("ascii")}
    try:
        producer.send(topic, value=record).get(timeout=15)
    finally:
        producer.close()


def _run_with_retries(operation, *, description, topic, partition, offset):
    for attempt in range(1, MAX_MESSAGE_ATTEMPTS + 1):
        try:
            return operation()
        except Exception:
            if attempt == MAX_MESSAGE_ATTEMPTS:
                raise
            delay = min(2 ** (attempt - 1), 4)
            LOGGER.exception(
                "%s failed topic=%s partition=%s offset=%s attempt=%s/%s; retrying in %ss",
                description, topic, partition, offset, attempt, MAX_MESSAGE_ATTEMPTS, delay,
            )
            time.sleep(delay)


def consume(topic=None, bootstrap_servers=None, group_id=None, consumer_factory=None, handler=None, dead_letter_handler=None):
    load_dotenv(config.PROJECT_ROOT / ".env")
    topic = topic or os.getenv("FRAUD_ALERTS_TOPIC")
    bootstrap_servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    group_id = group_id or os.getenv("KAFKA_INVESTIGATION_CONSUMER_GROUP", "fraud-investigation-service")
    dead_letter_topic = os.getenv("FRAUD_INVESTIGATION_DLQ_TOPIC", "fraud-investigation-dead-letter")
    if not topic: raise ValueError("FRAUD_ALERTS_TOPIC must be configured")
    if consumer_factory is None:
        from kafka import KafkaConsumer
        consumer_factory = KafkaConsumer
    consumer = consumer_factory(topic, bootstrap_servers=bootstrap_servers.split(","), group_id=group_id,
        enable_auto_commit=False, auto_offset_reset=os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest"),
        max_poll_records=1, value_deserializer=lambda raw: raw)
    handler = handler or investigate_alert
    dead_letter_handler = dead_letter_handler or _send_dead_letter
    LOGGER.info("Investigation consumer started topic=%s group=%s", topic, group_id)
    try:
        while True:
            for partition, messages in consumer.poll(timeout_ms=1000, max_records=1).items():
                for message in messages:
                    try:
                        alert = _decode_alert(message.value)
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
                        try:
                            _run_with_retries(
                                lambda: dead_letter_handler(bootstrap_servers, dead_letter_topic, message, "malformed_alert"),
                                description="Dead-letter write",
                                topic=topic,
                                partition=partition,
                                offset=message.offset,
                            )
                            count("kafka", "dead_letter", "success")
                            consumer.commit()
                            LOGGER.warning("Malformed alert sent to investigation dead-letter topic; source_offset=%s", message.offset)
                        except Exception as exc:
                            count("kafka", "dead_letter", "failure")
                            LOGGER.exception(
                                "Could not persist malformed alert after %s attempts; stopping with source offset uncommitted",
                                MAX_MESSAGE_ATTEMPTS,
                            )
                            consumer.seek(partition, message.offset)
                            raise RuntimeError(
                                f"Dead-letter write failed for {partition} offset {message.offset}; "
                                "source offset remains uncommitted."
                            ) from exc
                        continue
                    try:
                        result = _run_with_retries(
                            lambda: handler(alert),
                            description="Investigation",
                            topic=topic,
                            partition=partition,
                            offset=message.offset,
                        )
                        if (not isinstance(result, dict) or not result.get("alert_id") or
                                not result.get("investigation_id") or
                                result.get("investigation_status") not in {
                                    "completed", "partial", "insufficient_evidence", "failed"
                                }):
                            raise ValueError("Investigation handler returned no durable terminal result.")
                        # A failed LLM result is durable and explicitly marked failed.
                        consumer.commit()
                        LOGGER.info("Investigation offset committed alert_id=%s investigation_id=%s status=%s",
                            result.get("alert_id"), result.get("investigation_id"), result.get("investigation_status"))
                    except Exception as exc:
                        count("kafka", "consume", "failure")
                        LOGGER.exception(
                            "Investigation failed after %s attempts; stopping with source offset uncommitted",
                            MAX_MESSAGE_ATTEMPTS,
                        )
                        consumer.seek(partition, message.offset)
                        raise RuntimeError(
                            f"Investigation failed for {partition} offset {message.offset}; "
                            "source offset remains uncommitted."
                        ) from exc
    finally:
        consumer.close()


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from rag.metrics import start_metrics_server
    # Expose metrics while Kafka reconnects; failed records remain uncommitted.
    start_metrics_server()
    while True:
        try:
            consume()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            LOGGER.exception("Investigation consumer stopped; reconnecting in 5 seconds")
            time.sleep(5)


if __name__ == "__main__": main()
