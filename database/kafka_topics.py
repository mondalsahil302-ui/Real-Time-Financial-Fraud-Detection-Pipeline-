"""Idempotent Kafka topic provisioning for the fraud detection pipeline."""
from __future__ import annotations

import logging
import os
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

LOGGER = logging.getLogger(__name__)

REQUIRED_TOPICS = [
    (os.getenv("TRANSACTIONS_TOPIC", "transactions"), 6),
    (os.getenv("FRAUD_ALERTS_TOPIC", "fraud-alerts"), 6),
    (os.getenv("LOW_RISK_TOPIC", "low-risk-transactions"), 6),
    (os.getenv("INVESTIGATION_RESULTS_TOPIC", "investigation-results"), 6),
    (os.getenv("FRAUD_INVESTIGATION_DLQ_TOPIC", "fraud-investigation-dead-letter"), 1),
]


def ensure_topics(bootstrap_servers: str | None = None) -> None:
    """Ensure all required pipeline topics exist on the Kafka cluster."""
    servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    server_list = [s.strip() for s in servers.split(",") if s.strip()]
    if not server_list:
        server_list = ["localhost:9092"]

    try:
        admin = KafkaAdminClient(bootstrap_servers=server_list, client_id="topic-initializer")
    except Exception as exc:
        LOGGER.warning("Could not connect KafkaAdminClient to %s: %s", server_list, exc)
        return

    try:
        existing = set(admin.list_topics())
        to_create = []
        for name, partitions in REQUIRED_TOPICS:
            if name not in existing:
                to_create.append(NewTopic(name=name, num_partitions=partitions, replication_factor=1))

        if to_create:
            admin.create_topics(to_create, validate_only=False)
            LOGGER.info("Created missing Kafka topics: %s", [t.name for t in to_create])
        else:
            LOGGER.info("All required Kafka topics exist.")
    except TopicAlreadyExistsError:
        pass
    except Exception as exc:
        LOGGER.warning("Could not auto-create Kafka topics: %s", exc)
    finally:
        admin.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_topics()

