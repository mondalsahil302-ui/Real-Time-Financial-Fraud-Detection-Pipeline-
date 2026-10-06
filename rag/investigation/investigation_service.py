"""Application service joining retrieval, local LLM, artifact, and Cassandra."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache

from rag import config
from rag.investigation.investigation_schema import validate_result
from rag.investigation.llm_investigator import investigate_context
from rag.investigation.llm_provider import GeminiProvider
from rag.investigation.process_alert import save_context
from rag.retrieval.orchestrator import RetrievalOrchestrator
from rag.metrics import count

LOGGER = logging.getLogger(__name__)


class InvestigationRepository:
    """Use the shared Cassandra connection and the existing table columns."""
    def __init__(self, session=None):
        self.session, self.cluster = session, None

    def _session(self):
        if self.session is None:
            from database.cassandra_connection import get_session
            self.cluster, self.session = get_session()
        return self.session

    def get_existing(self, alert_id: str):
        from database.cassandra_connection import get_cassandra_config
        session = self._session()
        statement = session.prepare(f"SELECT investigation_id, llm_explanation FROM {get_cassandra_config().keyspace}.investigation_results WHERE alert_id = ? LIMIT 1")
        row = session.execute(statement, (alert_id,)).one()
        if row is None: return None
        raw = row.llm_explanation if hasattr(row, "llm_explanation") else row.get("llm_explanation")
        try: return json.loads(raw)
        except (TypeError, json.JSONDecodeError): return {"investigation_id": getattr(row, "investigation_id", ""), "alert_id": alert_id}

    def save(self, result: dict, context: dict):
        from database.cassandra_connection import get_cassandra_config
        result = validate_result(result)
        session = self._session()
        keyspace = get_cassandra_config().keyspace
        cql = f"INSERT INTO {keyspace}.investigation_results (alert_id, generated_at, investigation_id, transaction_id, retrieved_context, retrieved_documents, retrieval_count, llm_explanation, investigation_summary, risk_reasoning, recommended_review_points, investigation_status, llm_model, rag_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        statement = session.prepare(cql)
        sources = list(context.get("regulatory_context", []))
        paysim = context.get("historical_paysim_context", {})
        sources.extend(paysim if isinstance(paysim, list) else paysim.get("fraud_cases", []) + paysim.get("normal_cases", []))
        session.execute(statement, (result["alert_id"], datetime.fromisoformat(result["generated_at"]),
            result["investigation_id"], result["transaction_id"], json.dumps(context, default=str), json.dumps(sources, default=str),
            int(context.get("evidence_summary", {}).get("total_evidence_items", len(result["evidence"]))), json.dumps(result, ensure_ascii=False), result["investigation_summary"],
            json.dumps(result["risk_factors"], ensure_ascii=False), json.dumps(result["recommended_review_points"], ensure_ascii=False),
            result["investigation_status"], result["llm_model"], result["rag_version"]))

    def close(self):
        if self.cluster and self.session:
            from database.cassandra_connection import close_connection
            close_connection(self.cluster, self.session)
            self.cluster = self.session = None


@lru_cache(maxsize=1)
def _shared_components():
    return RetrievalOrchestrator(), GeminiProvider(), InvestigationRepository()


def investigate_alert(alert: dict, orchestrator=None, llm_provider=None, repository=None, save_artifacts: bool = True) -> dict:
    """Run retrieval and investigation end-to-end; persist before returning."""
    from rag.retrieval.normalization import normalize_alert
    normalized = normalize_alert(alert)
    shared = _shared_components() if orchestrator is None or llm_provider is None or repository is None else None
    orchestrator = orchestrator or shared[0]
    llm_provider = llm_provider or shared[1]
    repository = repository or shared[2]
    existing = repository.get_existing(normalized["alert_id"]) if hasattr(repository, "get_existing") else None
    if existing and existing.get("investigation_id"):
        LOGGER.info("Duplicate investigation skipped alert_id=%s investigation_id=%s", normalized["alert_id"], existing["investigation_id"])
        return existing
    context = orchestrator.process(normalized)
    context_path = None
    if save_artifacts:
        context_path = save_context(context)
        context["artifact_path"] = str(context_path)
    result = investigate_context(context, llm_provider)
    retryable_llm_categories = {
        "endpoint_unavailable", "llm_unavailable", "llm_timeout", "http_error",
        "malformed_provider_response", "invalid_model_response",
    }
    if result.get("investigation_status") == "failed" and result.get("error_category") in retryable_llm_categories:
        LOGGER.warning("Retrying LLM failure once category=%s", result["error_category"])
        result = investigate_context(context, llm_provider)
    validate_result(result)
    try:
        repository.save(result, context)
        count("cassandra", "write", "success")
        count("investigation", "completed", result["investigation_status"])
    except Exception:
        count("cassandra", "write", "failure")
        raise
    if save_artifacts:
        out = context_path.with_name(f"{context_path.stem}_result.json")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = context["evidence_summary"]
    LOGGER.info("Investigation complete alert_id=%s transaction_id=%s retrieval_counts=%s model=%s status=%s investigation_id=%s",
                normalized["alert_id"], normalized.get("transaction_id"), counts, result["llm_model"], result["investigation_status"], result["investigation_id"])
    return result
