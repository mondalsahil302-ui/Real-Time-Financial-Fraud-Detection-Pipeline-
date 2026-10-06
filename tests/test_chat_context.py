from __future__ import annotations

from backend.app.chat import _intent, _transaction_context


def _transaction():
    return {
        "transaction_id": "TX-1",
        "batch_id": "BATCH-1",
        "risk_level": "L5",
        "anomaly_score": 0.9,
        "xgboost_probability": 0.8,
        "xgboost_prediction": 1,
        "final_prediction": 1,
        "decision_path": "isolation_forest",
        "final_decision": "FRAUD_ALERT",
        "payload": {
            "event_time": "2026-10-05T00:00:00+00:00",
            "type": "TRANSFER",
            "amount": 2500.0,
            "nameOrig": "C-1",
            "nameDest": "C-2",
            "oldbalanceOrg": 3000.0,
            "newbalanceOrig": 500.0,
            "oldbalanceDest": 100.0,
            "newbalanceDest": 2600.0,
            "risk_action": "CRITICAL_INVESTIGATE",
            "model_version": "model-v1",
        },
    }


def test_question_intent_routes_regulatory_and_historical_questions():
    assert _intent("What does RBI say about EWS?") == "regulatory"
    assert _intent("Compare with historical fraud cases") == "historical"
    assert _intent("What happened with this account before?") == "account"


def test_transaction_context_prioritizes_authoritative_values_and_skips_paysim(monkeypatch):
    from rag.retrieval.cassandra_retriever import CassandraRetriever
    from rag.retrieval.knowledge_retriever import KnowledgeRetriever
    from rag.retrieval.paysim_retriever import PaySimRetriever

    class Cassandra:
        def retrieve(self, alert):
            assert alert["name_orig"] == "C-1"
            return {
                "recent_transactions": [{"transaction_id": "TX-OLD", "amount": 10}],
                "recent_alerts": [],
                "investigation_history": [],
            }

    class Knowledge:
        def retrieve(self, alert, query=None):
            assert "Why was this transaction flagged?" in query
            return [{
                "document_id": "RBI-1",
                "text": "Retrieved regulatory text.",
                "source": "RBI",
                "metadata": {
                    "authority": "RBI",
                    "source_type": "primary_regulatory",
                    "title": "EWS guidance",
                    "section": "Section 2",
                    "version": "2026",
                },
            }]

    class PaySim:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("PaySim must not be retrieved for an ordinary transaction question")

    monkeypatch.setattr(CassandraRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(CassandraRetriever, "retrieve", Cassandra.retrieve)
    monkeypatch.setattr(KnowledgeRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(KnowledgeRetriever, "retrieve", Knowledge.retrieve)
    monkeypatch.setattr(PaySimRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(PaySimRetriever, "retrieve", PaySim.retrieve)

    evidence, missing = _transaction_context(
        _transaction(),
        question="Why was this transaction flagged?",
        include_cassandra=True,
        include_fraud_knowledge=True,
        include_paysim_cases=True,
    )

    assert evidence[0]["source_type"] == "authoritative_current_transaction"
    assert evidence[0]["content"]["transaction_id"] == "TX-1"
    assert evidence[0]["content"]["batch_id"] == "BATCH-1"
    assert evidence[0]["content"]["final_decision_path"] == "isolation_forest"
    assert evidence[0]["content"]["risk_action"] == "CRITICAL_INVESTIGATE"
    assert any(item["source_type"] == "cassandra_history" for item in evidence)
    assert any(item["source_type"] == "fraud_knowledge" for item in evidence)
    assert not any("paysim" in item["source_type"] for item in evidence)
    assert "No relevant history was retrieved." not in missing


def test_regulatory_context_rejects_non_rbi_sources():
    from backend.app.chat import _knowledge_evidence

    items = [
        {
            "document_id": "secondary",
            "text": "Secondary view",
            "metadata": {"authority": "other", "source_type": "secondary_analysis"},
        },
        {
            "document_id": "rbi",
            "text": "Primary RBI text",
            "metadata": {"authority": "RBI", "source_type": "primary_regulatory"},
        },
    ]

    evidence = _knowledge_evidence(items, require_rbi=True)

    assert [item["source_id"] for item in evidence] == ["rbi"]


def test_historical_context_separates_fraud_and_normal_paysim(monkeypatch):
    from rag.retrieval.cassandra_retriever import CassandraRetriever
    from rag.retrieval.knowledge_retriever import KnowledgeRetriever
    from rag.retrieval.paysim_retriever import PaySimRetriever

    class Cassandra:
        def retrieve(self, alert):
            return {"recent_transactions": [], "recent_alerts": [], "investigation_history": []}

    class Knowledge:
        def retrieve(self, alert, query=None):
            return []

    paysim_calls = []

    class PaySim:
        def retrieve(self, alert, query=None, label=None):
            paysim_calls.append(label)
            return [{
                "document_id": f"case-{label}",
                "source_row_id": f"row-{label}",
                "text": f"Synthetic {label} case",
                "metadata": {"label": label, "dataset": "PaySim"},
            }]

    monkeypatch.setattr(CassandraRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(CassandraRetriever, "retrieve", Cassandra.retrieve)
    monkeypatch.setattr(KnowledgeRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(KnowledgeRetriever, "retrieve", Knowledge.retrieve)
    monkeypatch.setattr(PaySimRetriever, "__init__", lambda self: None)
    monkeypatch.setattr(PaySimRetriever, "retrieve", PaySim.retrieve)
    evidence, _ = _transaction_context(
        _transaction(),
        question="Compare this with historical fraud cases",
        include_cassandra=True,
        include_fraud_knowledge=True,
        include_paysim_cases=True,
    )

    assert paysim_calls == ["fraud", "normal"]
    assert {item["source_type"] for item in evidence} >= {
        "synthetic_paysim_fraud",
        "synthetic_paysim_normal",
    }
