"""Mocked-LLM regressions using the checked-in synthetic offline RAG context."""
import json
from pathlib import Path

import pytest

from rag.investigation.llm_investigator import investigate_context, investigate_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "rag_output" / "investigations" / "rag_test_transfer_context.json"


class MockLLM:
    model = "mock-investigator"

    def __init__(self, result=None):
        self.result = result or {
            "investigation_summary": "The current alert is high risk according to the supplied model outputs. The transaction has a substantial origin-balance reduction and destination-balance increase. Retrieved RBI 2024 material discusses EWS/RFA and transaction monitoring, but does not define this exact pattern as an RBI-prescribed indicator.",
            "evidence": [],
            "risk_factors": ["The current alert has an Isolation Forest anomaly score of 0.94."],
            "counter_evidence": ["A similar historical normal PaySim transaction with comparable transfer behavior was retrieved."],
            "missing_evidence": ["No relevant Cassandra account history was retrieved."],
            "historical_comparison": {"fraud_cases": [], "normal_cases": []}, "regulatory_references": [],
            "uncertainties": [], "recommended_review_points": ["Review applicable customer/account information available to the authorized investigator."],
        }

    def generate(self, prompt, system_prompt=None):
        assert "Do not infer or copy current model outputs into historical PaySim cases" in system_prompt
        assert "HISTORICAL PAYSIM FRAUD CASES" in prompt
        return "```json\n" + json.dumps(self.result) + "\n```"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_offline_fixture_creates_structured_result_without_cassandra_write(tmp_path):
    context = fixture()
    source = tmp_path / "rag_test_transfer_context.json"
    source.write_text(json.dumps(context), encoding="utf-8")
    result = investigate_file(source, llm=MockLLM(), persist=False)
    saved = json.loads((tmp_path / "rag_test_transfer_result.json").read_text(encoding="utf-8"))
    assert result == saved
    assert result["alert_id"] == "rag_test_transfer_context"
    assert result["transaction_id"] == "RAG_TEST_TXN_0001"
    assert result["alert_assessment"]["xgboost_probability"] == 0.91
    assert result["investigation_status"] == "partial"
    assert result["historical_comparison"].keys() == {"fraud_cases", "normal_cases"}
    assert any("No relevant account history was retrieved" in x for x in result["missing_evidence"])
    assert any("No previous alerts were retrieved" in x for x in result["missing_evidence"])
    assert result["counter_evidence"]


def test_regression_blocks_rbi_balance_attribution_and_historical_model_leakage():
    context = fixture()
    cases = context["historical_paysim_context"]
    bad_id = cases[0]["document_id"]
    response = MockLLM({
        "investigation_summary": "RBI says a large origin-balance decrease and destination-balance increase indicate suspicious activity.", "evidence": [],
        "risk_factors": [], "counter_evidence": ["No previous alerts exist."],
        "missing_evidence": [],
        "historical_comparison": {"fraud_cases": [], "normal_cases": [
            {"source_id": bad_id, "comparison": "Similar PaySim case had anomaly_score 0.94 and high Isolation Forest score."}]},
        "regulatory_references": [], "uncertainties": [], "recommended_review_points": ["Check the customer's occupation, city, and KYC status."]})
    result = investigate_context(context, response)
    summary = result["investigation_summary"].lower()
    assert "does not define this exact pattern" in summary
    comparison = json.dumps(result["historical_comparison"]).lower()
    assert "anomaly_score" not in comparison and "isolation forest" not in comparison
    assert not any("no previous alerts" in x.lower() for x in result["counter_evidence"])
    assert any("no previous alerts were retrieved" in x.lower() for x in result["missing_evidence"])
    points = " ".join(result["recommended_review_points"]).lower()
    assert "occupation" not in points and "city" not in points and "kyc status" not in points


def test_prompt_and_output_do_not_claim_empty_retrieval_proves_absence():
    result = investigate_context(fixture(), MockLLM())
    serialized = json.dumps(result).lower()
    assert "no previous alerts exist" not in serialized
    assert "no previous investigations exist" not in serialized
    assert "no relevant account history was retrieved from cassandra" in serialized


def test_bad_model_json_returns_controlled_failed_result():
    class Bad:
        model = "mock"
        def generate(self, prompt, system_prompt=None): return "not JSON"
    result = investigate_context(fixture(), Bad())
    assert result["investigation_status"] == "failed"
    assert result["error_category"] == "invalid_model_response"
    assert "missing_evidence" in result


def test_llm_duration_is_observed_on_success_and_failure(monkeypatch):
    class Timer:
        def __init__(self, metric): self.metric = metric
        def __enter__(self): return self
        def __exit__(self, *exc): self.metric.observations += 1

    class Duration:
        def __init__(self): self.observations = 0
        def labels(self, *labels): return self
        def time(self): return Timer(self)

    duration = Duration()
    monkeypatch.setattr("rag.investigation.llm_investigator.DURATION", duration)

    assert investigate_context(fixture(), MockLLM())["investigation_status"] == "partial"

    class Bad:
        model = "mock"
        def generate(self, prompt, system_prompt=None): return "not JSON"

    assert investigate_context(fixture(), Bad())["investigation_status"] == "failed"

    class Unexpected:
        model = "mock"
        def generate(self, prompt, system_prompt=None): raise RuntimeError("unexpected provider failure")

    with pytest.raises(RuntimeError, match="unexpected provider failure"):
        investigate_context(fixture(), Unexpected())
    assert duration.observations == 3


def test_missing_required_model_key_is_reported_without_fabrication():
    response = MockLLM({"investigation_summary": "Review this alert."})
    result = investigate_context(fixture(), response)
    assert result["investigation_status"] == "failed"
    assert result["error_category"] == "invalid_model_response"
    assert result["missing_key"] == "evidence"
    assert result["evidence"] == []


def test_offline_file_saves_controlled_raw_response_for_validation_failure(tmp_path):
    class MissingKey(MockLLM):
        def __init__(self): super().__init__({"investigation_summary": "missing fields"})
    source = tmp_path / "rag_test_transfer_context.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    result = investigate_file(source, llm=MissingKey(), persist=False)
    debug = tmp_path / "debug_llm_response_rag_test_transfer_context.txt"
    assert result["missing_key"] == "evidence"
    assert debug.read_text(encoding="utf-8").startswith("```")


def test_probability_or_paysim_similarity_cannot_become_fraud_proof():
    from rag.investigation.llm_investigator import _guard_claim
    assert "do not establish fraud" in _guard_claim("PaySim similarity proves fraud and XGBoost probability confirms it", summary=True)
    assert "not proof" in _guard_claim("Model output proves fraud")


def test_parser_accepts_clean_fenced_and_surrounded_json():
    from rag.investigation.llm_investigator import _parse_json
    assert _parse_json('{"ok": true}') == {"ok": True}
    assert _parse_json('```json\n{"ok": true}\n```') == {"ok": True}
    assert _parse_json('Result follows: {"ok": true} Done.') == {"ok": True}
