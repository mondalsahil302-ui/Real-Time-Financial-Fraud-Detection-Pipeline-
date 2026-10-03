"""Shared Kafka-to-Cassandra consumer runtime."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from cassandra.cluster import Cluster, Session
from cassandra.query import PreparedStatement
from kafka import KafkaConsumer
from kafka.structs import OffsetAndMetadata, TopicPartition

from database.cassandra_connection import close_connection, get_session

logger = logging.getLogger(__name__)

RowBuilder = Callable[[Mapping[str, Any]], tuple[Any, ...]]


def parse_event_time(value: Any) -> datetime:
    """Parse ISO-8601 timestamps emitted by Spark and normalize to UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event_time must be a non-empty ISO-8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"event_time is not valid ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def required_payload_fields(payload: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    """Reject missing/empty required fields without stopping the consumer."""
    missing = [
        field for field in fields
        if payload.get(field) is None or payload.get(field) == ""
    ]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))


def _decode_record(value: bytes | None) -> Mapping[str, Any]:
    if value is None:
        raise ValueError("Kafka record has a null value")
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Kafka value is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kafka JSON value must be an object")
    return payload


def run_consumer(
    *,
    topic: str,
    group_id: str,
    insert_cql: str,
    required_fields: tuple[str, ...],
    row_builder: RowBuilder,
    service_name: str,
) -> None:
    """Persist records and commit each Kafka offset only after Cassandra write."""
    from os import getenv

    bootstrap_servers = getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    offset_reset = getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("cassandra").setLevel(logging.WARNING)
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset=offset_reset,
        max_poll_records=1,
        client_id=service_name,
    )

    cluster: Cluster | None = None
    session: Session | None = None
    try:
        cluster, session = get_session()
        statement: PreparedStatement = session.prepare(insert_cql)
        logger.info(
            "%s consuming topic=%s group=%s broker=%s",
            service_name,
            topic,
            group_id,
            bootstrap_servers,
        )
        while True:
            records = consumer.poll(timeout_ms=1000, max_records=1)
            for partition_records in records.values():
                for record in partition_records:
                    partition = TopicPartition(record.topic, record.partition)
                    try:
                        payload = _decode_record(record.value)
                        required_payload_fields(payload, required_fields)
                        values = row_builder(payload)
                    except (TypeError, ValueError, KeyError) as exc:
                        # Leave the offset uncommitted. A later valid record can
                        # move the committed position forward; restarts replay it.
                        logger.error(
                            "%s skipped malformed record topic=%s partition=%d offset=%d: %s",
                            service_name,
                            record.topic,
                            record.partition,
                            record.offset,
                            exc,
                        )
                        continue

                    try:
                        session.execute(statement, values)
                        consumer.commit({
                            partition: OffsetAndMetadata(record.offset + 1, None)
                        })
                        logger.info(
                            "%s persisted transaction_id=%s topic=%s partition=%d offset=%d",
                            service_name,
                            payload.get("transaction_id"),
                            record.topic,
                            record.partition,
                            record.offset,
                        )
                    except Exception:
                        logger.exception(
                            "%s Cassandra write/offset commit failed at %s-%d-%d; retrying",
                            service_name,
                            record.topic,
                            record.partition,
                            record.offset,
                        )
                        consumer.seek(partition, record.offset)
                        time.sleep(2)
    except KeyboardInterrupt:
        logger.info("%s stopping after Ctrl+C", service_name)
    finally:
        try:
            consumer.close()
        finally:
            if cluster is not None and session is not None:
                close_connection(cluster, session)


def utc_now() -> datetime:
    """Return an aware UTC timestamp for Cassandra timestamp columns."""
    return datetime.now(timezone.utc)
