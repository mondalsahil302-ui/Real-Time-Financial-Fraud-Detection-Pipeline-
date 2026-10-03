"""Offline retrieval-context demo using a clearly synthetic alert."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.investigation.process_alert import process_alert


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    alert = {
        "transaction_id": "RAG_TEST_TXN_0001", "alert_id": "rag_test_transfer_context",
        "event_time": "2026-01-15T10:30:00+00:00", "type": "TRANSFER",
        "nameOrig": "RAG_TEST_ACCOUNT_ORIGIN", "nameDest": "RAG_TEST_ACCOUNT_DESTINATION",
        "amount": 125000.0, "oldbalanceOrg": 130000.0, "newbalanceOrig": 5000.0,
        "oldbalanceDest": 1000.0, "newbalanceDest": 126000.0,
        "anomaly_score": 0.94, "risk_level": "HIGH", "risk_action": "ALERT",
        "xgboost_probability": 0.91, "final_prediction": True,
        "final_decision_path": "RAG_TEST_SYNTHETIC", "final_risk_action": "REVIEW",
        "model_version": "rag-test", "source": "rag_test", "alert_reason": "synthetic offline demo",
    }
    context = process_alert(alert)
    print("===== ALERT =====")
    print(json.dumps(context["alert"], indent=2, ensure_ascii=False))
    print("\n===== CASSANDRA CONTEXT =====")
    print(json.dumps(context["live_account_context"], indent=2, ensure_ascii=False, default=str))
    print("\n===== RBI KNOWLEDGE =====")
    print(json.dumps(context["regulatory_context"], indent=2, ensure_ascii=False))
    print("\n===== PAYSIM HISTORICAL CASES =====")
    print(json.dumps(context["historical_paysim_context"], indent=2, ensure_ascii=False))
    print("\n===== FINAL INVESTIGATION CONTEXT =====")
    print(json.dumps({"artifact_path": context["artifact_path"], "retrieval_status": context["retrieval_status"],
                      "evidence_summary": context["evidence_summary"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
