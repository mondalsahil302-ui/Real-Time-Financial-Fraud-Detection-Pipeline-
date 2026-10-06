"""Write/read/delete one uniquely named synthetic result against Cassandra."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from database.cassandra_connection import get_cassandra_config
from rag.investigation.investigation_schema import validate_result
from rag.investigation.investigation_service import InvestigationRepository


def main() -> int:
    suffix = uuid.uuid4().hex
    alert_id, investigation_id = f"RAG_TEST_ALERT_{suffix}", str(uuid.uuid4())
    generated = datetime.now(timezone.utc)
    generated = generated.replace(microsecond=(generated.microsecond // 1000) * 1000)
    result = validate_result({"investigation_id": investigation_id, "alert_id": alert_id, "transaction_id": f"RAG_TEST_TXN_{suffix}",
        "generated_at": generated.isoformat(), "investigation_summary": "Synthetic persistence verification only.",
        "alert_assessment": {"risk_level": None, "model_prediction": None, "anomaly_score": None, "xgboost_probability": None, "decision_path": None},
        "evidence": [], "risk_factors": [], "counter_evidence": [], "missing_evidence": [], "historical_comparison": {"fraud_cases": [], "normal_cases": []},
        "regulatory_references": [], "uncertainties": [], "recommended_review_points": [], "investigation_status": "completed",
        "llm_model": "persistence-smoke-test", "rag_version": "test"})
    context = {"source": "rag_test", "regulatory_context": [], "historical_paysim_context": {"fraud_cases": [], "normal_cases": []}}
    repository = InvestigationRepository()
    keyspace = get_cassandra_config().keyspace
    session = None
    try:
        repository.save(result, context)
        session = repository._session()
        found = session.execute(f"SELECT investigation_id, llm_explanation FROM {keyspace}.investigation_results WHERE alert_id = %s AND generated_at = %s AND investigation_id = %s",
            (alert_id, generated, investigation_id)).one()
        if found is None or json.loads(found.llm_explanation)["investigation_id"] != investigation_id:
            raise RuntimeError("Structured investigation read-back failed")
        print(f"Cassandra investigation persistence: SUCCESS (synthetic alert_id={alert_id})")
        return 0
    finally:
        if session is not None:
            session.execute(f"DELETE FROM {keyspace}.investigation_results WHERE alert_id = %s AND generated_at = %s AND investigation_id = %s",
                (alert_id, generated, investigation_id))
        repository.close()


if __name__ == "__main__": raise SystemExit(main())
