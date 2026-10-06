import pytest

from rag.investigation.investigation_schema import InvestigationSchemaError, validate_result
from rag.investigation.investigation_schema import validate_llm_payload


def valid_result():
    return {"investigation_id": "i", "alert_id": "a", "transaction_id": "t", "generated_at": "now",
        "investigation_summary": "Review", "alert_assessment": {"risk_level": None, "final_prediction": None,
        "anomaly_score": None, "xgboost_probability": None, "decision_path": None}, "risk_factors": [],
        "counter_evidence": [], "missing_evidence": [], "historical_comparison": {"fraud_cases": [], "normal_cases": []},
        "regulatory_references": [], "uncertainties": [], "recommended_review_points": [],
        "investigation_status": "insufficient_evidence", "llm_model": "m", "rag_version": "v"}


def test_rejects_unsupported_or_invalid_result_fields():
    with pytest.raises(InvestigationSchemaError):
        validate_result({"arbitrary": "free form"})


def test_requires_separate_missing_evidence_and_historical_groups():
    value = valid_result()
    del value["missing_evidence"]
    with pytest.raises(InvestigationSchemaError):
        validate_result(value)
    value = valid_result()
    value["historical_comparison"] = []
    with pytest.raises(InvestigationSchemaError):
        validate_result(value)


def test_rejects_unknown_evidence_type():
    value = valid_result()
    value["evidence"] = [{"source_type": "model_output_unknown", "source_id": "x", "finding": "score"}]
    with pytest.raises(InvestigationSchemaError):
        validate_result(value)


def model_payload():
    return {"investigation_summary": "Review using supplied evidence.", "evidence": [], "risk_factors": [],
        "counter_evidence": [], "missing_evidence": [], "historical_comparison": {"fraud_cases": [], "normal_cases": []},
        "regulatory_references": [], "uncertainties": [], "recommended_review_points": []}


def test_llm_schema_accepts_empty_evidence_but_reports_missing_or_invalid_fields():
    assert validate_llm_payload(model_payload())["evidence"] == []
    missing = model_payload(); del missing["missing_evidence"]
    with pytest.raises(InvestigationSchemaError) as exc:
        validate_llm_payload(missing)
    assert exc.value.missing_key == "missing_evidence"
    wrong = model_payload(); wrong["risk_factors"] = "high"
    with pytest.raises(InvestigationSchemaError) as exc:
        validate_llm_payload(wrong)
    assert exc.value.invalid_field == "risk_factors"


def test_llm_schema_rejects_unknown_extra_fields():
    value = model_payload(); value["untrusted_extra"] = True
    with pytest.raises(InvestigationSchemaError) as exc:
        validate_llm_payload(value)
    assert exc.value.invalid_field == "untrusted_extra"
