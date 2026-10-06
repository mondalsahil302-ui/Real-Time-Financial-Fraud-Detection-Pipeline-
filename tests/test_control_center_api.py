from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_control_center_health_and_batch_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    def fake_producer(*args, **kwargs):
        return SimpleNamespace(cancelled=False, sent_count=0, generated_count=0, failed_count=0)

    app = create_app(db_path=tmp_path / "control.sqlite3", start_workers=False, producer=fake_producer)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        llm_status = client.get("/api/llm/status")
        assert llm_status.status_code == 200
        assert llm_status.json()["provider"] == "gemini"
        assert llm_status.json()["available"] is False
        assert llm_status.json()["fallback"] == "none"
        assert "GEMINI_API_KEY is not configured" in llm_status.json()["detail"]

        invalid = client.post("/api/batches", json={"count": 0, "delay": 0.05})
        assert invalid.status_code == 422

        headers = {"Idempotency-Key": "demo-batch-1"}
        payload = {"count": 10, "delay": 0.05, "source": "frontend_simulator"}
        created = client.post("/api/batches", json=payload, headers=headers)
        replayed = client.post("/api/batches", json=payload, headers=headers)
        assert created.status_code == 202
        assert replayed.status_code == 202
        assert created.json()["batch_id"] == replayed.json()["batch_id"]
        assert created.json()["requested_count"] == 10


def test_chat_response_only_returns_citations_from_retrieved_evidence(tmp_path):
    from backend.app.chat import answer_chat
    from backend.app.schemas import AssistantChatRequest
    from backend.app.storage import Store

    store = Store(tmp_path / "chat.sqlite3")
    store.transaction = lambda transaction_id: {"transaction_id": "TX-1", "payload": {"amount": 12}}
    saved = []
    store.save_chat_message = lambda *args: saved.append(args)

    class Provider:
        model = "test-model"
        def generate(self, prompt, system_prompt=None):
            return '{"answer":"Evidence based answer","evidence_ids":["real-source","invented-source"],"uncertainties":[]}'

    evidence = [{"source_type": "fraud_knowledge", "source_id": "real-source", "content": "Retrieved fact"}]
    body = AssistantChatRequest(question="Why was this flagged?", transaction_id="TX-1")
    response = answer_chat(body, store, provider=Provider(), retrieval=lambda transaction, request: (evidence, []))
    assert response["answer"] == "Evidence based answer"
    assert [item["source_id"] for item in response["evidence"]] == ["real-source"]
    assert response["retrieval_count"] == 1
    assert len(saved) == 2


def test_chat_reports_the_gemini_provider_that_answered(monkeypatch, tmp_path):
    from backend.app.chat import answer_chat
    from backend.app.schemas import AssistantChatRequest
    from backend.app.storage import Store

    store = Store(tmp_path / "chat-provider.sqlite3")
    store.chat_messages = lambda _: []
    store.transaction = lambda _: {"transaction_id": "TX-1", "payload": {}}
    saved = []
    store.save_chat_message = lambda *args: saved.append(args)

    class Gemini:
        provider = "gemini"
        model = "gemini-3.5-flash-lite"

        def generate(self, prompt, system_prompt=None):
            return '{"answer":"Used retrieved facts.","evidence_ids":["source-1"],"uncertainties":[]}'

    evidence = [{"source_type": "fraud_knowledge", "source_id": "source-1", "content": "fact"}]
    monkeypatch.setattr(
        "backend.app.chat._provider_chain",
        lambda _: ([Gemini()], []),
    )
    response = answer_chat(
        AssistantChatRequest(question="What does the evidence say?", transaction_id="TX-1"),
        store,
        retrieval=lambda *_: (evidence, []),
    )

    assert response["llm_provider"] == "gemini"
    assert response["llm_model"] == "gemini-3.5-flash-lite"
    assert response["evidence"] == evidence
    assert len(saved) == 2


def test_prometheus_non_finite_values_are_json_null(monkeypatch):
    import json

    from backend.app import monitoring

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {"result": [
                {"metric": {"job": "spark"}, "value": ["0", "NaN"]},
                {"metric": {"job": "producer"}, "value": ["0", "Infinity"]},
                {"metric": {"job": "api"}, "value": ["0", "-Infinity"]},
                {"metric": {"job": "cassandra"}, "value": ["0", "2.5"]},
            ]}}

    monkeypatch.setattr(monitoring.httpx, "get", lambda *args, **kwargs: Response())

    values = monitoring._prom_query("test")

    assert [item["value"] for item in values] == [None, None, None, 2.5]
    assert json.dumps(values, allow_nan=False)


def test_empty_prometheus_query_is_a_valid_unavailable_metric(monkeypatch):
    import json

    from backend.app import monitoring

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(monitoring.httpx, "get", lambda *args, **kwargs: Response())

    result = monitoring.metric("transactions_per_second")

    assert result["available"] is False
    assert result["values"] == []
    assert json.dumps(result, allow_nan=False)
