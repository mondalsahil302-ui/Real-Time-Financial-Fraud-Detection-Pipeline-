"""Bounded queries against the existing Cassandra account-history tables."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache

from rag import config
from rag.retrieval.reranker import deduplicate, rank_recent

LOGGER = logging.getLogger(__name__)

ALERT_COLUMNS = ("name_orig", "event_time", "alert_id", "transaction_id", "event_date", "event_hour", "transaction_type", "name_dest", "amount", "old_balance_orig", "new_balance_orig", "old_balance_dest", "new_balance_dest", "anomaly_score", "risk_level", "risk_action", "alert_required", "xgboost_probability", "xgboost_prediction", "final_prediction", "final_decision_path", "final_risk_action", "model_version", "status", "created_at")
TRANSACTION_COLUMNS = ("name_orig", "event_time", "transaction_id", "event_date", "event_hour", "transaction_type", "name_dest", "amount", "old_balance_orig", "new_balance_orig", "old_balance_dest", "new_balance_dest", "anomaly_score", "risk_level", "risk_action", "xgboost_probability", "xgboost_prediction", "final_prediction", "final_decision_path", "model_version", "source", "inserted_at")
INVESTIGATION_COLUMNS = ("alert_id", "generated_at", "investigation_id", "transaction_id", "retrieved_context", "retrieved_documents", "retrieval_count", "llm_explanation", "investigation_summary", "risk_reasoning", "recommended_review_points", "investigation_status", "llm_model", "rag_version")


def _as_dict(row) -> dict:
    if row is None:
        return {}
    values = row._asdict() if hasattr(row, "_asdict") else (dict(row) if isinstance(row, dict) else vars(row))
    result = {}
    for key, value in values.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, datetime):
            result[key] = value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
        else:
            result[key] = str(value)
    return result


@lru_cache(maxsize=1)
def _shared_session():
    from database.cassandra_connection import get_session
    return get_session()


class CassandraRetriever:
    def __init__(self, session=None):
        self.session = session
        self.cluster = None
        self._statements = {}

    def _get_session(self):
        if self.session is None:
            self.cluster, self.session = _shared_session()
        return self.session

    def _query(self, key, cql, values):
        session = self._get_session()
        statement = self._statements.get(key)
        if statement is None:
            statement = session.prepare(cql)
            self._statements[key] = statement
        return [_as_dict(row) for row in session.execute(statement, values)]

    def retrieve(self, alert: dict) -> dict:
        """Read by Cassandra partition keys only; never scan or join tables."""
        account = alert.get("name_orig")
        alert_id = alert.get("alert_id")
        if not account:
            return {"current_alert": dict(alert), "recent_transactions": [], "recent_alerts": [], "investigation_history": [], "retrieval_note": "origin account missing; Cassandra account-partition queries skipped"}
        keyspace = __import__("database.cassandra_connection", fromlist=["get_cassandra_config"]).get_cassandra_config().keyspace
        quoted_alert = ", ".join(ALERT_COLUMNS)
        quoted_txn = ", ".join(TRANSACTION_COLUMNS)
        quoted_investigation = ", ".join(INVESTIGATION_COLUMNS)
        alerts = self._query("recent_alerts", f"SELECT {quoted_alert} FROM {keyspace}.fraud_alerts WHERE name_orig = ? LIMIT ?", (str(account), config.CASSANDRA_RECENT_ALERT_LIMIT))
        current = next((row for row in alerts if row.get("alert_id") == alert_id or (alert.get("transaction_id") and row.get("transaction_id") == alert.get("transaction_id"))), None)
        if current is None and alert.get("event_time"):
            event_time = datetime.fromisoformat(str(alert["event_time"]).replace("Z", "+00:00"))
            if event_time.tzinfo is not None:
                event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
            current_rows = self._query("current_alert", f"SELECT {quoted_alert} FROM {keyspace}.fraud_alerts WHERE name_orig = ? AND event_time = ? AND alert_id = ? LIMIT 1", (str(account), event_time, str(alert_id)))
            current = current_rows[0] if current_rows else None
        if current:
            alerts = [row for row in alerts if row.get("alert_id") != current.get("alert_id")]
        transactions = self._query("recent_transactions", f"SELECT {quoted_txn} FROM {keyspace}.transactions WHERE name_orig = ? LIMIT ?", (str(account), config.CASSANDRA_RECENT_TRANSACTION_LIMIT))
        transactions = rank_recent(transactions, ("transaction_id",), config.RAG_MAX_CONTEXT_TRANSACTIONS)
        alerts = rank_recent(alerts, ("alert_id",), config.RAG_MAX_CONTEXT_ALERTS)
        investigation_rows = []
        investigation_ids = deduplicate([{"alert_id": row.get("alert_id")} for row in ([current] if current else []) + alerts], ("alert_id",))
        for item in investigation_ids:
            if not item.get("alert_id"):
                continue
            investigation_rows.extend(self._query("investigations", f"SELECT {quoted_investigation} FROM {keyspace}.investigation_results WHERE alert_id = ? LIMIT ?", (str(item["alert_id"]), config.CASSANDRA_RECENT_ALERT_LIMIT)))
        investigation_rows = rank_recent(investigation_rows, ("investigation_id",), config.RAG_MAX_CONTEXT_ALERTS)
        return {"current_alert": current or dict(alert), "recent_transactions": transactions, "recent_alerts": alerts,
                "investigation_history": investigation_rows}
