"""Semantic regulatory/domain retrieval from the fraud_knowledge collection."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from functools import lru_cache

import chromadb

from rag import config
from rag.embedder import LocalEmbedder
from rag.retrieval.reranker import rank_knowledge

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _shared_embedder():
    return LocalEmbedder(config.EMBEDDING_MODEL)


def build_knowledge_query(alert: dict) -> str:
    """Describe only alert fields and arithmetic directly supported by them."""
    fields = []
    if alert.get("transaction_type"):
        fields.append(f"transaction type {alert['transaction_type']}")
    if alert.get("risk_level"):
        fields.append(f"risk level {alert['risk_level']}")
    if alert.get("anomaly_score") is not None:
        fields.append(f"anomaly score {alert['anomaly_score']}")
    if alert.get("risk_action"):
        fields.append(f"risk action {alert['risk_action']}")
    if alert.get("alert_reason"):
        fields.append(f"alert reason {alert['alert_reason']}")
    old = alert.get("old_balance_orig")
    new = alert.get("new_balance_orig")
    if old is not None and new is not None:
        try:
            delta = Decimal(str(new)) - Decimal(str(old))
            fields.append(f"origin balance changed from {old} to {new} (change {format(delta, 'f')})")
        except (InvalidOperation, ValueError):
            fields.append(f"origin balance before {old} and after {new}")
    for key, label in (("final_decision_path", "decision path"), ("final_risk_action", "final risk action")):
        if alert.get(key):
            fields.append(f"{label} {alert[key]}")
    topics = ["EWS and RFA", "transaction monitoring", "fraud investigation", "fraud classification"]
    txn_type = str(alert.get("transaction_type", "")).upper()
    if txn_type in {"TRANSFER", "CASH_OUT", "CASHOUT", "PAYMENT", "DEBIT"}:
        topics.append("digital banking and payment fraud")
    prefix = "; ".join(fields) if fields else "fraud alert"
    return f"{prefix}. Retrieve applicable RBI and domain guidance on {', '.join(topics)}. Treat alert fields as observed evidence."


class KnowledgeRetriever:
    def __init__(self, collection=None, embedder=None, client=None):
        self.collection = collection
        self.embedder = embedder
        self.client = client

    def _collection(self):
        if self.collection is None:
            self.client = self.client or chromadb.PersistentClient(path=str(config.VECTOR_DB_PATH))
            self.collection = self.client.get_collection(config.COLLECTION_KNOWLEDGE)
        return self.collection

    def retrieve(self, alert: dict, query: str | None = None) -> list[dict]:
        query = query or build_knowledge_query(alert)
        embedder = self.embedder or _shared_embedder()
        collection = self._collection()
        count = collection.count()
        if count == 0:
            return []
        candidates = min(count, config.RAG_TOP_K_KNOWLEDGE * config.RAG_CANDIDATE_MULTIPLIER)
        raw = collection.query(query_embeddings=embedder.encode([query]), n_results=candidates,
                               include=["documents", "metadatas", "distances"])
        items = []
        for doc_id, text, metadata, distance in zip(raw["ids"][0], raw["documents"][0], raw["metadatas"][0], raw["distances"][0]):
            if config.RAG_MAX_KNOWLEDGE_DISTANCE is not None and distance > config.RAG_MAX_KNOWLEDGE_DISTANCE:
                continue
            items.append({"document_id": doc_id, "text": text, "metadata": metadata or {}, "distance": float(distance),
                          "source": (metadata or {}).get("source_file", (metadata or {}).get("relative_path", "unknown"))})
        ranked = rank_knowledge(items, config.RAG_MAX_KNOWLEDGE_CHUNKS)
        LOGGER.info("fraud_knowledge returned %d evidence items", len(ranked))
        return ranked
