import json
import uuid

from rag.investigation.process_alert import process_alert
from rag.retrieval.cassandra_retriever import CassandraRetriever
from rag.retrieval.context_builder import build_context
from rag.retrieval.knowledge_retriever import KnowledgeRetriever, build_knowledge_query
from rag.retrieval.normalization import normalize_alert
from rag.retrieval.orchestrator import RetrievalOrchestrator
from rag.retrieval.paysim_retriever import build_paysim_query
from rag.retrieval.reranker import deduplicate, rank_knowledge, rank_paysim


def sample_alert():
    return {
        "transaction_id": "txn-1", "event_time": "2026-01-15T10:30:00+00:00", "type": "TRANSFER",
        "nameOrig": "C1", "nameDest": "C2", "amount": 1000.0, "oldbalanceOrg": 1200.0,
        "newbalanceOrig": 200.0, "oldbalanceDest": 10.0, "newbalanceDest": 1010.0,
        "risk_level": "HIGH", "anomaly_score": 0.9, "risk_action": "ALERT",
        "xgboost_probability": 0.8, "final_decision_path": "IF_XGB", "source": "rag_test",
    }


def test_alert_normalization_uses_actual_kafka_fields_and_deterministic_id():
    alert = normalize_alert(sample_alert())
    assert alert["transaction_type"] == "TRANSFER"
    assert "type" not in alert and "nameOrig" not in alert
    assert alert["name_orig"] == "C1"
    assert alert["old_balance_orig"] == 1200.0
    assert alert["event_date"] == "2026-01-15"
    assert alert["event_hour"] == 10
    assert alert["alert_id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "fraud-alert:txn-1"))


def test_knowledge_query_is_alert_specific_and_uses_present_fields_only():
    alert = normalize_alert(sample_alert())
    query = build_knowledge_query(alert)
    assert "TRANSFER" in query and "HIGH" in query and "0.9" in query
    assert "origin balance changed from 1200.0 to 200.0 (change -1000.0)" in query
    assert "CASH_OUT" not in query


def test_paysim_query_marks_examples_as_synthetic_reference():
    query = build_paysim_query(normalize_alert(sample_alert()))
    assert "TRANSFER" in query and "amount 1000.0" in query
    assert "Synthetic historical reference only" in query
    assert "prove" not in query.lower()


class FakeEmbedder:
    def encode(self, texts, batch_size=64):
        return [[0.1, 0.2] for _ in texts]


class FakeCollection:
    def count(self):
        return 3

    def query(self, **kwargs):
        return {
            "ids": [["historical", "secondary", "current"]],
            "documents": [["old guidance", "analysis", "RBI primary guidance"]],
            "metadatas": [[
                {"status": "historical", "source_type": "historical_reference", "authority": "RBI", "current_authority": False, "source_file": "old.pdf", "version": "2016"},
                {"status": "reference", "source_type": "secondary_analysis", "authority": "PwC", "current_authority": False, "source_file": "analysis.pdf", "version": "2024"},
                {"status": "current", "source_type": "primary_regulatory", "authority": "RBI", "current_authority": True, "source_file": "current.pdf", "version": "2024"},
            ]],
            "distances": [[0.01, 0.02, 0.4]],
        }


def test_knowledge_retriever_preserves_metadata_and_prioritizes_current_rbi(monkeypatch):
    monkeypatch.setattr("rag.retrieval.knowledge_retriever.config.RAG_TOP_K_KNOWLEDGE", 3)
    monkeypatch.setattr("rag.retrieval.knowledge_retriever.config.RAG_MAX_KNOWLEDGE_CHUNKS", 3)
    retriever = KnowledgeRetriever(collection=FakeCollection(), embedder=FakeEmbedder())
    results = retriever.retrieve(normalize_alert(sample_alert()))
    assert [item["document_id"] for item in results] == ["current", "secondary", "historical"]
    assert results[0]["metadata"]["status"] == "current"
    assert results[-1]["metadata"]["status"] == "historical"
    assert results[0]["distance"] == 0.4


def test_historical_material_is_supplementary_to_current_material():
    ranked = rank_knowledge([
        {"document_id": "historic", "distance": 0.01, "metadata": {"status": "historical", "source_type": "historical_reference"}},
        {"document_id": "current", "distance": 0.7, "metadata": {"status": "current", "current_authority": True, "authority": "RBI", "source_type": "primary_regulatory"}},
    ])
    assert [item["document_id"] for item in ranked] == ["current", "historic"]


class FakeSession:
    def __init__(self):
        self.queries = []

    def prepare(self, cql):
        return cql

    def execute(self, statement, values):
        self.queries.append((statement, values))
        if ".fraud_alerts " in statement:
            return [{"alert_id": "alert-current", "transaction_id": "txn-1", "event_time": "2026-01-15T10:30:00+00:00", "name_orig": "C1"}]
        if ".transactions " in statement:
            return [
                {"transaction_id": "txn-old", "event_time": "2026-01-14T10:30:00+00:00", "name_orig": "C1"},
                {"transaction_id": "txn-new", "event_time": "2026-01-15T10:30:00+00:00", "name_orig": "C1"},
            ]
        if ".investigation_results " in statement:
            return [{"investigation_id": "inv-1", "alert_id": "alert-current", "generated_at": "2026-01-15T11:00:00+00:00"}]
        return []


def test_cassandra_retriever_uses_partition_queries_normalizes_and_deduplicates():
    session = FakeSession()
    context = CassandraRetriever(session=session).retrieve(normalize_alert({**sample_alert(), "alert_id": "alert-current"}))
    assert context["current_alert"]["alert_id"] == "alert-current"
    assert [item["transaction_id"] for item in context["recent_transactions"]] == ["txn-new", "txn-old"]
    assert context["recent_alerts"] == []  # current alert is kept in its own field
    assert context["investigation_history"][0]["investigation_id"] == "inv-1"
    assert all("WHERE name_orig = ?" in statement or "WHERE alert_id = ?" in statement for statement, _ in session.queries)


def test_deduplication_and_paysim_ranking_are_deterministic():
    items = [
        {"document_id": "a", "source_row_id": "1", "distance": 0.4, "metadata": {"transaction_type": "PAYMENT", "amount": "1000", "origin_balance_depleted": False}},
        {"document_id": "b", "source_row_id": "2", "distance": 0.8, "metadata": {"transaction_type": "TRANSFER", "amount": "1100", "origin_balance_depleted": False}},
        {"document_id": "dup", "source_row_id": "2", "distance": 0.1, "metadata": {"transaction_type": "TRANSFER", "amount": "1000", "origin_balance_depleted": False}},
    ]
    assert len(deduplicate(items, ("source_row_id",))) == 2
    ranked = rank_paysim(items, normalize_alert(sample_alert()))
    assert ranked[0]["source_row_id"] == "2"
    assert [item["source_row_id"] for item in ranked] == [item["source_row_id"] for item in rank_paysim(items, normalize_alert(sample_alert()))]


def test_paysim_balance_ranking_prefers_matching_partial_reduction_over_depletion():
    alert = normalize_alert(sample_alert())  # origin 1200 -> 200: a partial reduction
    items = [
        {"document_id": "depleted", "source_row_id": "1", "distance": 0.01,
         "metadata": {"transaction_type": "TRANSFER", "amount": "1000", "origin_balance_depleted": True,
                      "origin_balance_unchanged": False, "balance_change_amount": "-1200",
                      "destination_balance_increased": True, "destination_balance_unchanged": False}},
        {"document_id": "partial", "source_row_id": "2", "distance": 0.5,
         "metadata": {"transaction_type": "TRANSFER", "amount": "1000", "origin_balance_depleted": False,
                      "origin_balance_unchanged": False, "balance_change_amount": "-800",
                      "destination_balance_increased": True, "destination_balance_unchanged": False}},
    ]
    ranked = rank_paysim(items, alert)
    assert ranked[0]["source_row_id"] == "2"
    assert ranked[0]["ranking_reason"]["balance_behavior_match_score"] == 1.0


def test_context_schema_separates_evidence_and_strips_secrets():
    alert = normalize_alert({**sample_alert(), "api_token": "must-not-save"})
    context = build_context(alert, {"current_alert": alert, "recent_transactions": [{"transaction_id": "txn-2", "password": "hidden"}]},
                            [{"document_id": "k1", "text": "current rule", "distance": 0.2, "metadata": {"authority": "RBI", "status": "current", "version": "2024"}}],
                            [{"document_id": "p1", "text": "synthetic case", "distance": 0.3, "source_row_id": "17", "metadata": {"label": "fraud", "source_row_id": "17"}}],
                            {"cassandra": "success", "fraud_knowledge": "success", "paysim_cases": "success"})
    assert context["context_version"] == "1.0"
    assert "api_token" not in json.dumps(context)
    assert "password" not in json.dumps(context)
    assert context["regulatory_context"][0]["status"] == "current"
    assert context["historical_paysim_context"][0]["evidence_kind"] == "synthetic_historical_reference"
    assert context["evidence_summary"]["total_evidence_items"] == 4


class FakeRetriever:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result or [], error, []

    def retrieve(self, alert, query=None):
        self.calls.append((alert, query))
        if self.error:
            raise self.error
        return self.result


def test_orchestrator_handles_failures_independently_and_does_not_call_an_llm(tmp_path):
    cassandra = FakeRetriever(error=ConnectionError("private connection info"))
    knowledge = FakeRetriever(result=[{"document_id": "k1", "text": "RBI current", "distance": 0.1, "metadata": {"status": "current", "authority": "RBI"}}])
    paysim = FakeRetriever(result=[{"document_id": "p1", "source_row_id": "5", "text": "historical synthetic", "distance": 0.2, "metadata": {"source_row_id": "5", "label": "fraud"}}])
    context = process_alert(sample_alert(), orchestrator=RetrievalOrchestrator(cassandra, knowledge, paysim), output_dir=tmp_path)
    artifact = json.loads((tmp_path / f"{context['alert']['alert_id']}.json").read_text(encoding="utf-8"))
    assert context["retrieval_status"] == {"cassandra": "failed", "fraud_knowledge": "success", "paysim_cases": "success"}
    assert context["regulatory_context"] and context["historical_paysim_context"]
    assert "private connection info" not in json.dumps(artifact)
    assert "llm_explanation" not in artifact
    assert len(knowledge.calls) == 1 and len(paysim.calls) == 1


def test_chroma_failure_does_not_block_cassandra_or_other_collection():
    cassandra = FakeRetriever(result={"current_alert": {"alert_id": "a1"}, "recent_transactions": [], "recent_alerts": [], "investigation_history": []})
    knowledge = FakeRetriever(error=RuntimeError("embedding failure"))
    paysim = FakeRetriever(result=[{"document_id": "p1", "source_row_id": "1", "metadata": {"source_row_id": "1"}}])
    context = RetrievalOrchestrator(cassandra, knowledge, paysim).process(sample_alert())
    assert context["retrieval_status"] == {"cassandra": "success", "fraud_knowledge": "failed", "paysim_cases": "success"}
    assert context["historical_paysim_context"][0]["source_row_id"] == "1"
    assert context["regulatory_context"] == []
