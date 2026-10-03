"""Create the fraud detection keyspace and tables idempotently."""

from __future__ import annotations

import logging
from pathlib import Path

from database.cassandra_connection import (
    close_connection,
    get_cassandra_config,
    get_system_session,
)

logger = logging.getLogger(__name__)
SCHEMA_PATH = Path(__file__).with_name("schema.cql")


def _statements() -> list[str]:
    """Read semicolon-delimited CQL, excluding full-line comments."""
    source_lines = [
        line for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    ]
    return [part.strip() for part in "\n".join(source_lines).split(";") if part.strip()]


def create_schema() -> None:
    """Apply all non-destructive schema statements from schema.cql."""
    cluster, session = get_system_session()
    try:
        for statement in _statements():
            session.execute(statement)
            if statement.upper().startswith("CREATE KEYSPACE"):
                session.set_keyspace(get_cassandra_config().keyspace)
            logger.info("Applied schema statement: %s", statement.splitlines()[0])
    finally:
        close_connection(cluster, session)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    create_schema()
    logger.info("Cassandra schema is ready in keyspace %s", get_cassandra_config().keyspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
