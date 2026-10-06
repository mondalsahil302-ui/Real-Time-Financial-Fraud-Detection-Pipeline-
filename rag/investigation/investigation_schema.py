"""Strict validation and normalization for investigation results."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class InvestigationSchemaError(ValueError):
    def __init__(self, message: str, *, missing_key: str | None = None, invalid_field: str | None = None):
        super().__init__(message)
        self.missing_key = missing_key
        self.invalid_field = invalid_field


SOURCE_TYPES = {"live_transaction", "cassandra_history", "model_output", "rbi_knowledge",
                "paysim_fraud", "paysim_normal", "missing_evidence"}
STATUSES = {"completed", "partial", "insufficient_evidence", "failed"}


def alert_assessment(alert: dict) -> dict:
    return {"risk_level": alert.get("risk_level"), "model_prediction": alert.get("final_prediction"),
            "anomaly_score": alert.get("anomaly_score"), "xgboost_probability": alert.get("xgboost_probability"),
            "decision_path": alert.get("final_decision_path")}


def validate_llm_payload(value: Any) -> dict:
    """Reject incomplete/wrong-type model payloads before normalization."""
    if not isinstance(value, dict):
        raise InvestigationSchemaError("LLM response must be an object", invalid_field="root")
    required = ("investigation_summary", "evidence", "risk_factors", "counter_evidence", "missing_evidence",
                "historical_comparison", "regulatory_references", "uncertainties", "recommended_review_points")
    allowed = set(required)
    if set(value) - allowed:
        extra = sorted(set(value) - allowed)[0]
        raise InvestigationSchemaError(f"unsupported LLM response field: {extra}", invalid_field=extra)
    for key in required:
        if key not in value:
            raise InvestigationSchemaError(f"LLM response is missing required key: {key}", missing_key=key)
    if not isinstance(value["investigation_summary"], str) or not value["investigation_summary"].strip():
        raise InvestigationSchemaError("investigation_summary must be a non-empty string", invalid_field="investigation_summary")
    for key in ("evidence", "risk_factors", "counter_evidence", "missing_evidence", "regulatory_references", "uncertainties", "recommended_review_points"):
        if not isinstance(value[key], list):
            raise InvestigationSchemaError(f"{key} must be an array", invalid_field=key)
    for key in ("risk_factors", "counter_evidence", "missing_evidence", "uncertainties", "recommended_review_points"):
        if any(not isinstance(item, str) for item in value[key]):
            raise InvestigationSchemaError(f"{key} must contain strings", invalid_field=key)
    if not isinstance(value["historical_comparison"], dict):
        raise InvestigationSchemaError("historical_comparison must be an object", invalid_field="historical_comparison")
    if any(not isinstance(value["historical_comparison"].get(group), list) for group in ("fraud_cases", "normal_cases")):
        raise InvestigationSchemaError("historical_comparison needs fraud_cases and normal_cases arrays", invalid_field="historical_comparison")
    if not isinstance(value["evidence"], list) or any(not isinstance(item, dict) or item.get("source_type") not in SOURCE_TYPES or not item.get("source_id") or not isinstance(item.get("finding"), str) for item in value["evidence"]):
        raise InvestigationSchemaError("evidence must contain source_type, source_id, and finding objects", invalid_field="evidence")
    for group in ("fraud_cases", "normal_cases"):
        if any(not isinstance(item, dict) or not isinstance(item.get("source_id"), str) or not isinstance(item.get("comparison"), str) for item in value["historical_comparison"][group]):
            raise InvestigationSchemaError(f"historical_comparison.{group} items need source_id and comparison strings", invalid_field="historical_comparison")
    if any(not isinstance(x, dict) for x in value["regulatory_references"]):
        raise InvestigationSchemaError("regulatory_references must contain objects", invalid_field="regulatory_references")
    if any(not isinstance(item.get("source_id"), str) or not isinstance(item.get("reference"), str) for item in value["regulatory_references"]):
        raise InvestigationSchemaError("regulatory references need source_id and reference strings", invalid_field="regulatory_references")
    return value


def validate_result(value: Any) -> dict:
    if not isinstance(value, dict):
        raise InvestigationSchemaError("result must be a JSON object")
    allowed = {"investigation_id", "alert_id", "transaction_id", "generated_at", "investigation_summary", "alert_assessment",
        "evidence", "risk_factors", "counter_evidence", "missing_evidence", "historical_comparison", "regulatory_references", "uncertainties",
        "recommended_review_points", "investigation_status", "llm_model", "rag_version", "error_category", "missing_key", "invalid_field"}
    if set(value) - allowed:
        raise InvestigationSchemaError("result contains unsupported field(s): " + ", ".join(sorted(set(value) - allowed)))
    required = {"investigation_summary", "alert_assessment", "evidence", "risk_factors", "counter_evidence", "missing_evidence", "historical_comparison",
                "regulatory_references", "uncertainties", "recommended_review_points", "investigation_id", "alert_id", "transaction_id",
                "generated_at", "investigation_status", "llm_model", "rag_version"}
    missing = sorted(required - set(value))
    if missing:
        raise InvestigationSchemaError("missing required field(s): " + ", ".join(missing))
    if not isinstance(value["investigation_summary"], str) or not value["investigation_summary"].strip():
        raise InvestigationSchemaError("investigation_summary must be a non-empty string")
    for field in ("risk_factors", "counter_evidence", "missing_evidence", "regulatory_references", "uncertainties", "recommended_review_points"):
        if not isinstance(value[field], list):
            raise InvestigationSchemaError(f"{field} must be an array")
    for field in ("risk_factors", "counter_evidence", "missing_evidence", "uncertainties", "recommended_review_points"):
        if not all(isinstance(item, str) and item.strip() for item in value[field]):
            raise InvestigationSchemaError(f"{field} must contain non-empty strings")
    if value["investigation_status"] not in STATUSES:
        raise InvestigationSchemaError("invalid investigation_status")
    if not isinstance(value["alert_assessment"], dict):
        raise InvestigationSchemaError("alert_assessment must be an object")
    assessment_fields = {"risk_level", "model_prediction", "anomaly_score", "xgboost_probability", "decision_path"}
    if assessment_fields - value["alert_assessment"].keys():
        raise InvestigationSchemaError("alert_assessment is missing required model-output fields")
    comparison = value["historical_comparison"]
    if not isinstance(comparison, dict) or set(comparison) != {"fraud_cases", "normal_cases"}:
        raise InvestigationSchemaError("historical_comparison must contain fraud_cases and normal_cases arrays")
    for group in ("fraud_cases", "normal_cases"):
        if not isinstance(comparison[group], list) or any(not isinstance(item, dict) or not {"source_id", "comparison"}.issubset(item) for item in comparison[group]):
            raise InvestigationSchemaError(f"historical_comparison.{group} items need source_id and comparison")
    if "evidence" in value:
        if not isinstance(value["evidence"], list):
            raise InvestigationSchemaError("evidence must be an array")
        for item in value["evidence"]:
            if not isinstance(item, dict) or item.get("source_type") not in SOURCE_TYPES or not item.get("source_id") or not isinstance(item.get("finding"), str):
                raise InvestigationSchemaError("each evidence item needs a valid source_type, source_id, and finding")
    regulatory_fields = {"source_id", "source_file", "source_pages", "authority", "status", "reference"}
    if not isinstance(value["regulatory_references"], list) or any(not isinstance(item, dict) or regulatory_fields - item.keys() for item in value["regulatory_references"]):
        raise InvestigationSchemaError("regulatory references are missing source metadata fields")
    return value


def failure_result(alert: dict, model: str, rag_version: str, error_category: str, *, missing_key: str | None = None, invalid_field: str | None = None) -> dict:
    return {"investigation_summary": "Investigation generation failed before a validated LLM assessment was available.",
            "evidence": [], "risk_factors": [], "counter_evidence": [], "missing_evidence": [],
            "historical_comparison": {"fraud_cases": [], "normal_cases": []}, "regulatory_references": [],
            "uncertainties": [f"LLM investigation unavailable ({error_category}); human review is required."],
            "recommended_review_points": ["Retry after resolving the LLM or response-validation error."],
            "investigation_status": "failed", "error_category": error_category,
            "alert_assessment": alert_assessment(alert), "investigation_id": "", "alert_id": str(alert.get("alert_id", "")),
            "transaction_id": str(alert.get("transaction_id", "")), "generated_at": datetime.now(timezone.utc).isoformat(),
            "llm_model": model, "rag_version": rag_version,
            **({"missing_key": missing_key} if missing_key else {}), **({"invalid_field": invalid_field} if invalid_field else {})}
