"""Schema metadata and idempotent insert/read/delete checks."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from database.cassandra_connection import (
    close_connection,
    get_cassandra_config,
    get_session,
)


class CassandraSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cluster, cls.session = get_session()
        cls.keyspace_name = get_cassandra_config().keyspace
        cls.keyspace = cls.cluster.metadata.keyspaces[cls.keyspace_name]

    @classmethod
    def tearDownClass(cls) -> None:
        close_connection(cls.cluster, cls.session)

    def test_all_required_tables_and_columns_exist(self) -> None:
        expected = {
            "transactions": {
                "transaction_id", "event_time", "name_orig", "event_date",
                "event_hour", "transaction_type", "name_dest", "amount",
                "old_balance_orig", "new_balance_orig", "old_balance_dest", "new_balance_dest",
                "anomaly_score", "risk_level", "risk_action", "xgboost_probability",
                "xgboost_prediction", "final_prediction", "final_decision_path",
                "model_version", "source", "inserted_at",
            },
            "fraud_alerts": {
                "alert_id", "transaction_id", "event_time", "name_orig", "name_dest",
                "anomaly_score", "risk_level", "risk_action", "alert_required",
                "xgboost_probability", "xgboost_prediction", "final_prediction",
                "final_decision_path", "final_risk_action", "model_version", "status", "created_at",
            },
            "investigation_results": {
                "investigation_id", "alert_id", "transaction_id", "generated_at",
                "retrieved_context", "retrieved_documents", "retrieval_count",
                "llm_explanation", "investigation_summary", "risk_reasoning",
                "recommended_review_points", "investigation_status", "llm_model", "rag_version",
            },
        }
        for table_name, required_columns in expected.items():
            with self.subTest(table=table_name):
                self.assertIn(table_name, self.keyspace.tables)
                actual = set(self.keyspace.tables[table_name].columns)
                self.assertTrue(required_columns.issubset(actual))

    def test_query_primary_keys(self) -> None:
        expected = {
            "transactions": (["name_orig"], ["event_time", "transaction_id"]),
            "fraud_alerts": (["name_orig"], ["event_time", "alert_id"]),
            "investigation_results": (["alert_id"], ["generated_at", "investigation_id"]),
        }
        for name, (partition, clustering) in expected.items():
            with self.subTest(table=name):
                metadata = self.keyspace.tables[name]
                self.assertEqual([column.name for column in metadata.partition_key], partition)
                self.assertEqual([column.name for column in metadata.clustering_key], clustering)

    def test_clustering_sort_order(self) -> None:
        expected = {
            "transactions": {"event_time": "desc", "transaction_id": "asc"},
            "fraud_alerts": {"event_time": "desc", "alert_id": "asc"},
            "investigation_results": {"generated_at": "desc", "investigation_id": "asc"},
        }
        for table_name, expected_order in expected.items():
            rows = self.session.execute(
                "SELECT column_name, clustering_order FROM system_schema.columns "
                "WHERE keyspace_name=%s AND table_name=%s",
                (self.keyspace_name, table_name),
            )
            actual = {
                row.column_name: row.clustering_order.lower()
                for row in rows
                if row.clustering_order != "none"
            }
            with self.subTest(table=table_name):
                self.assertEqual(actual, expected_order)

    def test_transactions_insert_select_delete(self) -> None:
        account = f"CASSANDRA_TEST_{uuid.uuid4()}"
        transaction_id = f"CASSANDRA_TEST_TRANSACTION_{uuid.uuid4()}"
        event_time = datetime.now(timezone.utc)
        try:
            self.session.execute(
                "INSERT INTO transactions (name_orig, event_time, transaction_id) VALUES (%s, %s, %s)",
                (account, event_time, transaction_id),
            )
            found = self.session.execute(
                "SELECT transaction_id FROM transactions "
                "WHERE name_orig=%s AND event_time=%s AND transaction_id=%s",
                (account, event_time, transaction_id),
            ).one()
            self.assertIsNotNone(found)
            self.assertEqual(found.transaction_id, transaction_id)
        finally:
            self.session.execute(
                "DELETE FROM transactions WHERE name_orig=%s AND event_time=%s AND transaction_id=%s",
                (account, event_time, transaction_id),
            )


if __name__ == "__main__":
    unittest.main()
