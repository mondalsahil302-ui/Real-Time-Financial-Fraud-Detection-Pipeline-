import json
from pathlib import Path

from rag.investigation.investigation_service import investigate_alert


class Orchestrator:
    def __init__(self, context): self.context, self.calls = context, 0
    def process(self, alert): self.calls += 1; return self.context


class Provider:
    model = "mock-model"
    def generate(self, prompt, system_prompt=None):
        return json.dumps({"investigation_summary":"Review indicated.","evidence":[],"risk_factors":[],"counter_evidence":[],"missing_evidence":[],
            "historical_comparison":{"fraud_cases":[],"normal_cases":[]},"regulatory_references":[],"uncertainties":[],"recommended_review_points":[]})


class Repository:
    def __init__(self, existing=None): self.existing, self.saved = existing, []
    def get_existing(self, alert_id): return self.existing
    def save(self, result, context): self.saved.append((result, context))


def fixture(): return json.loads(Path("rag_output/investigations/rag_test_transfer_context.json").read_text(encoding="utf-8"))


def test_service_retrieves_generates_and_persists_partial_result():
    context = fixture(); context["retrieval_status"]["cassandra"] = "failed"
    orch, repo = Orchestrator(context), Repository()
    result = investigate_alert(context["alert"], orch, Provider(), repo, save_artifacts=False)
    assert result["investigation_status"] == "partial"
    assert orch.calls == 1 and len(repo.saved) == 1


def test_duplicate_alert_skips_retrieval_and_persistence():
    existing = {"investigation_id":"prior", "alert_id":"rag_test_transfer_context"}
    orch, repo = Orchestrator(fixture()), Repository(existing)
    assert investigate_alert(fixture()["alert"], orch, Provider(), repo, save_artifacts=False) == existing
    assert orch.calls == 0 and repo.saved == []


def test_temporary_llm_failure_is_retried_once_then_persisted_as_failed():
    from rag.investigation.llm_provider import LLMProviderError
    class Offline:
        model = "offline"
        calls = 0
        def generate(self, prompt, system_prompt=None):
            self.calls += 1
            raise LLMProviderError("unavailable", "endpoint_unavailable")
    provider, repo = Offline(), Repository()
    result = investigate_alert(fixture()["alert"], Orchestrator(fixture()), provider, repo, save_artifacts=False)
    assert provider.calls == 2
    assert result["investigation_status"] == "failed"
    assert result["error_category"] == "endpoint_unavailable"
    assert len(repo.saved) == 1


def test_invalid_llm_json_is_retried_once_then_saved_as_controlled_failure():
    class Invalid:
        model = "invalid"
        calls = 0
        def generate(self, prompt, system_prompt=None):
            self.calls += 1
            return "not JSON"
    provider, repo = Invalid(), Repository()
    result = investigate_alert(fixture()["alert"], Orchestrator(fixture()), provider, repo, save_artifacts=False)
    assert provider.calls == 2
    assert result["investigation_status"] == "failed"
    assert len(repo.saved) == 1


def test_repository_maps_result_to_existing_cassandra_schema(monkeypatch):
    from rag.investigation.investigation_service import InvestigationRepository
    from database.cassandra_connection import CassandraConfig
    class Session:
        def __init__(self): self.calls = []
        def prepare(self, cql): return cql
        def execute(self, statement, values): self.calls.append((statement, values))
    monkeypatch.setattr("database.cassandra_connection.get_cassandra_config", lambda: CassandraConfig("localhost", 9042, "fraud_detection"))
    session = Session(); repository = InvestigationRepository(session)
    context = fixture()
    result = investigate_alert(context["alert"], Orchestrator(context), Provider(), Repository(), save_artifacts=False)
    repository.save(result, context)
    cql, values = session.calls[0]
    assert "fraud_detection.investigation_results" in cql
    assert "investigation_status" in cql and "retrieved_documents" in cql
    assert values[0] == result["alert_id"] and values[11] == result["investigation_status"]
    assert json.loads(values[7])["investigation_id"] == result["investigation_id"]
