"""Live connectivity checks for the configured local Cassandra service."""

from __future__ import annotations

import unittest

from database.cassandra_connection import (
    close_connection,
    get_cassandra_config,
    get_system_session,
)


class CassandraConnectionTests(unittest.TestCase):
    def test_cassandra_is_reachable_and_keyspace_exists(self) -> None:
        try:
            cluster, session = get_system_session()
        except Exception as exc:
            self.skipTest(f"Cassandra is not running locally: {exc}")
        try:
            row = session.execute("SELECT release_version FROM system.local").one()
            self.assertTrue(row.release_version)
            keyspace = get_cassandra_config().keyspace
            self.assertIn(keyspace, cluster.metadata.keyspaces)
        finally:
            close_connection(cluster, session)


if __name__ == "__main__":
    unittest.main()
