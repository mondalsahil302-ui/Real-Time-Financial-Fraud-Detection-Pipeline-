"""Orchestrate Cassandra and two separate Chroma retrievals without an LLM."""
from __future__ import annotations

import logging

from rag import config
from rag.retrieval.cassandra_retriever import CassandraRetriever
from rag.retrieval.context_builder import build_context
from rag.retrieval.knowledge_retriever import KnowledgeRetriever, build_knowledge_query
from rag.retrieval.normalization import normalize_alert
from rag.retrieval.paysim_retriever import PaySimRetriever, build_paysim_query
from rag.retrieval.reranker import rank_recent

LOGGER = logging.getLogger(__name__)


class RetrievalOrchestrator:
    def __init__(self, cassandra_retriever=None, knowledge_retriever=None, paysim_retriever=None):
        self.cassandra_retriever = cassandra_retriever or CassandraRetriever()
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.paysim_retriever = paysim_retriever or PaySimRetriever()

    def process(self, raw_alert: dict) -> dict:
        alert = normalize_alert(raw_alert)
        status, errors = {}, {}
        try:
            cassandra = self.cassandra_retriever.retrieve(alert)
            retrieval_note = cassandra.get("retrieval_note")
            cassandra = {
                "current_alert": cassandra.get("current_alert", alert),
                "recent_transactions": rank_recent(cassandra.get("recent_transactions", []), ("transaction_id",), config.RAG_MAX_CONTEXT_TRANSACTIONS),
                "recent_alerts": rank_recent(cassandra.get("recent_alerts", []), ("alert_id",), config.RAG_MAX_CONTEXT_ALERTS),
                "investigation_history": rank_recent(cassandra.get("investigation_history", []), ("investigation_id",), config.RAG_MAX_CONTEXT_ALERTS),
            }
            status["cassandra"] = "partial" if retrieval_note else "success"
            if retrieval_note:
                errors["cassandra"] = str(retrieval_note)
        except Exception as exc:
            LOGGER.warning("Cassandra retrieval failed for alert_id=%s (%s)", alert.get("alert_id"), type(exc).__name__)
            cassandra = {"current_alert": alert, "recent_transactions": [], "recent_alerts": [], "investigation_history": []}
            status["cassandra"] = "failed"
            errors["cassandra"] = f"{type(exc).__name__}: retrieval failed; check Cassandra service and logs"
        try:
            knowledge_query = build_knowledge_query(alert)
            knowledge = self.knowledge_retriever.retrieve(alert, knowledge_query)
            status["fraud_knowledge"] = "success"
        except Exception as exc:
            LOGGER.warning("fraud_knowledge retrieval failed for alert_id=%s (%s)", alert.get("alert_id"), type(exc).__name__)
            knowledge = []
            status["fraud_knowledge"] = "failed"
            errors["fraud_knowledge"] = f"{type(exc).__name__}: retrieval failed; check Chroma and local embedding model"
        try:
            paysim_query = build_paysim_query(alert)
            paysim = self.paysim_retriever.retrieve(alert, paysim_query)
            status["paysim_cases"] = "success"
        except Exception as exc:
            LOGGER.warning("paysim_cases retrieval failed for alert_id=%s (%s)", alert.get("alert_id"), type(exc).__name__)
            paysim = []
            status["paysim_cases"] = "failed"
            errors["paysim_cases"] = f"{type(exc).__name__}: retrieval failed; check Chroma and local embedding model"
        context = build_context(alert, cassandra, knowledge, paysim, status, errors)
        self._log_inventory(context)
        return context

    @staticmethod
    def _log_inventory(context):
        counts = context["evidence_summary"]
        alert = context["alert"]
        LOGGER.info("RAG retrieval alert_id=%s transaction_id=%s timestamp=%s", alert.get("alert_id"), alert.get("transaction_id"), context["retrieval_timestamp"])
        LOGGER.info("Cassandra counts transactions=%d alerts=%d investigations=%d", counts["recent_transaction_count"], counts["recent_alert_count"], counts["investigation_count"])
        LOGGER.info("Chroma counts fraud_knowledge=%d paysim_cases=%d total_evidence=%d", counts["knowledge_count"], counts["paysim_case_count"], counts["total_evidence_items"])
        LOGGER.info("Evidence source IDs: %s", {key: counts[key] for key in ("knowledge_document_ids", "paysim_document_ids", "cassandra_transaction_ids", "cassandra_alert_ids", "cassandra_investigation_ids")})
