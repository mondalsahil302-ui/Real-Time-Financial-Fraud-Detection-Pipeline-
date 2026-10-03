"""Assemble clearly separated, JSON-serializable evidence for later review."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items() if not _sensitive_key(str(k))}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sensitive_key(key: str) -> bool:
    folded = key.lower()
    return any(word in folded for word in ("password", "secret", "token", "credential", "private_key"))


def build_context(alert: dict, cassandra: dict, knowledge: list[dict], paysim: list[dict],
                  retrieval_status: dict, retrieval_errors: dict | None = None) -> dict:
    """Build evidence-only context with source provenance intact."""
    current = cassandra.get("current_alert") or alert
    live_context = {
        "current_alert": _json_value(current),
        "recent_transactions": _json_value(cassandra.get("recent_transactions", [])),
        "recent_alerts": _json_value(cassandra.get("recent_alerts", [])),
        "previous_investigations": _json_value(cassandra.get("investigation_history", [])),
    }
    regulatory = []
    for item in knowledge:
        metadata = item.get("metadata", {})
        regulatory.append(_json_value({"document_id": item.get("document_id"), "text": item.get("text"),
                                       "source": item.get("source"), "distance": item.get("distance"),
                                       "authority": metadata.get("authority"), "version": metadata.get("version"),
                                       "status": metadata.get("status"), "current_authority": metadata.get("current_authority"),
                                       "source_type": metadata.get("source_type"), "topic": metadata.get("topic"),
                                       "relative_path": metadata.get("relative_path"), "metadata": metadata,
                                       "ranking_reason": item.get("ranking_reason")}))
    historical = []
    for item in paysim:
        metadata = item.get("metadata", {})
        historical.append(_json_value({"document_id": item.get("document_id"), "text": item.get("text"),
                                       "source": item.get("source", "PaySim synthetic historical reference"),
                                       "source_row_id": item.get("source_row_id", metadata.get("source_row_id")),
                                       "transaction_type": metadata.get("transaction_type"), "label": metadata.get("label"),
                                       "distance": item.get("distance"), "metadata": metadata,
                                       "ranking_reason": item.get("ranking_reason"),
                                       "evidence_kind": "synthetic_historical_reference"}))
    model_fields = ("anomaly_score", "risk_level", "risk_action", "xgboost_probability", "xgboost_prediction",
                    "final_prediction", "final_decision_path", "final_risk_action", "model_version")
    model_output = {key: alert[key] for key in model_fields if key in alert}
    total_evidence = (1 + len(live_context["recent_transactions"]) + len(live_context["recent_alerts"])
                      + len(live_context["previous_investigations"]) + len(regulatory) + len(historical))
    return _json_value({
        "context_version": "1.0",
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "alert": alert,
        "live_account_context": live_context,
        "regulatory_context": regulatory,
        "historical_paysim_context": historical,
        "model_output": model_output,
        "evidence_categories": {
            "factual_live_data": ["alert", "live_account_context"],
            "regulatory_knowledge": ["regulatory_context"],
            "historical_synthetic_data": ["historical_paysim_context"],
            "model_output": ["model_output"],
        },
        "retrieval_status": retrieval_status,
        "retrieval_errors": retrieval_errors or {},
        "evidence_summary": {
            "current_alert_count": 1,
            "recent_transaction_count": len(live_context["recent_transactions"]),
            "recent_alert_count": len(live_context["recent_alerts"]),
            "investigation_count": len(live_context["previous_investigations"]),
            "knowledge_count": len(regulatory),
            "paysim_case_count": len(historical),
            "total_evidence_items": total_evidence,
            "knowledge_document_ids": [item.get("document_id") for item in regulatory],
            "paysim_document_ids": [item.get("document_id") for item in historical],
            "cassandra_transaction_ids": [item.get("transaction_id") for item in live_context["recent_transactions"]],
            "cassandra_alert_ids": [item.get("alert_id") for item in live_context["recent_alerts"]],
            "cassandra_investigation_ids": [item.get("investigation_id") for item in live_context["previous_investigations"]],
            "summary_type": "deterministic_retrieval_inventory",
        },
    })
