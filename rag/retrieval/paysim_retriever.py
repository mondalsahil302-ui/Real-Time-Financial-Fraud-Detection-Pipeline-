"""Semantic retrieval of synthetic PaySim cases; never live account evidence."""
from __future__ import annotations

import logging

import chromadb

from rag import config
from rag.retrieval.knowledge_retriever import _shared_embedder
from rag.retrieval.reranker import rank_paysim

LOGGER = logging.getLogger(__name__)


def build_paysim_query(alert: dict) -> str:
    parts = ["Historical PaySim examples with similar transaction characteristics"]
    if alert.get("transaction_type"):
        parts.append(f"transaction type {alert['transaction_type']}")
    if alert.get("amount") is not None:
        parts.append(f"amount {alert['amount']}")
    for field, label in (("risk_level", "risk level"), ("anomaly_score", "anomaly score"),
                         ("xgboost_probability", "XGBoost probability"), ("final_decision_path", "decision path")):
        if alert.get(field) is not None:
            parts.append(f"{label} {alert[field]}")
    for before, after, label in (("old_balance_orig", "new_balance_orig", "origin balance"),
                                 ("old_balance_dest", "new_balance_dest", "destination balance")):
        if alert.get(before) is not None and alert.get(after) is not None:
            parts.append(f"{label} from {alert[before]} to {alert[after]}")
    parts.append("Synthetic historical reference only; labels do not establish the status of the live alert.")
    return "; ".join(parts)


class PaySimRetriever:
    def __init__(self, collection=None, embedder=None, client=None):
        self.collection = collection
        self.embedder = embedder
        self.client = client

    def _collection(self):
        if self.collection is None:
            self.client = self.client or chromadb.PersistentClient(path=str(config.VECTOR_DB_PATH))
            self.collection = self.client.get_collection(config.COLLECTION_PAYSIM)
        return self.collection

    def retrieve(
        self,
        alert: dict,
        query: str | None = None,
        label: str | None = None,
    ) -> list[dict]:
        query = query or build_paysim_query(alert)
        embedder = self.embedder or _shared_embedder()
        collection = self._collection()
        where = {"label": label} if label else None
        count = collection.count()
        if count == 0:
            return []
        candidates = min(count, config.RAG_TOP_K_PAYSIM * config.RAG_CANDIDATE_MULTIPLIER)
        query_options = {
            "query_embeddings": embedder.encode([query]),
            "n_results": candidates,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_options["where"] = where
        raw = collection.query(**query_options)
        items = []
        for doc_id, text, metadata, distance in zip(raw["ids"][0], raw["documents"][0], raw["metadatas"][0], raw["distances"][0]):
            if config.RAG_MAX_PAYSIM_DISTANCE is not None and distance > config.RAG_MAX_PAYSIM_DISTANCE:
                continue
            metadata = metadata or {}
            items.append({"document_id": doc_id, "text": text, "metadata": metadata, "distance": float(distance),
                          "source_row_id": metadata.get("source_row_id"), "source": "PaySim synthetic historical reference"})
        ranked = rank_paysim(items, alert, config.RAG_MAX_PAYSIM_CASES)
        LOGGER.info("paysim_cases returned %d synthetic historical evidence items", len(ranked))
        return ranked
