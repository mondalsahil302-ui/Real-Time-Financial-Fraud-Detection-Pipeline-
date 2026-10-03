"""Shared Cassandra configuration and connection helpers."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cassandra import ProtocolVersion
from cassandra.cluster import Cluster, Session
from cassandra.policies import DCAwareRoundRobinPolicy
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CassandraConfig:
    """Connection settings read from the project environment."""

    host: str
    port: int
    keyspace: str


def get_cassandra_config() -> CassandraConfig:
    """Return Cassandra settings, with local Docker defaults."""
    host = os.getenv("CASSANDRA_HOST", "localhost").strip()
    keyspace = os.getenv("CASSANDRA_KEYSPACE", "fraud_detection").strip()
    try:
        port = int(os.getenv("CASSANDRA_PORT", "9042"))
    except ValueError as exc:
        raise ValueError("CASSANDRA_PORT must be an integer") from exc

    if not host:
        raise ValueError("CASSANDRA_HOST must not be empty")
    if not 1 <= port <= 65535:
        raise ValueError("CASSANDRA_PORT must be between 1 and 65535")
    if not keyspace:
        raise ValueError("CASSANDRA_KEYSPACE must not be empty")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", keyspace):
        raise ValueError("CASSANDRA_KEYSPACE must be a lowercase CQL identifier")
    return CassandraConfig(host=host, port=port, keyspace=keyspace)


def create_cluster() -> Cluster:
    """Create a local-driver Cluster without requiring a keyspace to exist."""
    config = get_cassandra_config()
    return Cluster(
        [config.host],
        port=config.port,
        protocol_version=ProtocolVersion.V5,
        load_balancing_policy=DCAwareRoundRobinPolicy(
            local_dc=os.getenv("CASSANDRA_LOCAL_DC", "datacenter1")
        ),
    )


def _connect(keyspace: str | None) -> tuple[Cluster, Session]:
    cluster = create_cluster()
    try:
        session = cluster.connect(keyspace) if keyspace else cluster.connect()
    except Exception:
        cluster.shutdown()
        logger.exception("Could not connect to Cassandra at %s", get_cassandra_config().host)
        raise
    return cluster, session


def get_system_session() -> tuple[Cluster, Session]:
    """Connect without selecting a keyspace (for schema creation)."""
    return _connect(None)


def get_session() -> tuple[Cluster, Session]:
    """Connect to the configured application keyspace."""
    return _connect(get_cassandra_config().keyspace)


def close_connection(cluster: Cluster, session: Session) -> None:
    """Close an owned session and its cluster cleanly."""
    try:
        session.shutdown()
    finally:
        cluster.shutdown()


def main() -> int:
    """Run a simple connectivity check for the README command."""
    logging.basicConfig(level=logging.INFO)
    cluster, session = get_system_session()
    try:
        row = session.execute("SELECT release_version FROM system.local").one()
        logger.info(
            "Connected to Cassandra %s at %s:%s",
            row.release_version,
            get_cassandra_config().host,
            get_cassandra_config().port,
        )
        return 0
    finally:
        close_connection(cluster, session)


if __name__ == "__main__":
    raise SystemExit(main())
