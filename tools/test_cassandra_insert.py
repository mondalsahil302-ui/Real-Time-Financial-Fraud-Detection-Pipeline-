"""Insert, read, and remove one synthetic row in each Cassandra table."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.cassandra_connection import close_connection, get_cassandra_config, get_session

KEYSPACE = get_cassandra_config().keyspace

logger = logging.getLogger("cassandra-smoke-test")
NOW = datetime.now(timezone.utc)
ORIGIN = "CASSANDRA_TEST_ORIGIN"
TRANSACTION_ID = "CASSANDRA_TEST_TRANSACTION"
ALERT_ID = "CASSANDRA_TEST_ALERT"
INVESTIGATION_ID = "CASSANDRA_TEST_INVESTIGATION"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cluster, session = get_session()
    try:
        statements = {
            "transaction_insert": session.prepare(
                f"INSERT INTO {KEYSPACE}.transactions (name_orig,event_time,transaction_id,event_date,event_hour,"
                "transaction_type,name_dest,amount,old_balance_orig,new_balance_orig,old_balance_dest,"
                "new_balance_dest,anomaly_score,risk_level,risk_action,xgboost_probability,"
                "xgboost_prediction,final_prediction,final_decision_path,model_version,source,inserted_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            ),
            "alert_insert": session.prepare(
                f"INSERT INTO {KEYSPACE}.fraud_alerts (name_orig,event_time,alert_id,transaction_id,event_date,event_hour,"
                "transaction_type,name_dest,amount,old_balance_orig,new_balance_orig,old_balance_dest,"
                "new_balance_dest,anomaly_score,risk_level,risk_action,alert_required,xgboost_probability,"
                "xgboost_prediction,final_prediction,final_decision_path,final_risk_action,model_version,status,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            ),
            "investigation_insert": session.prepare(
                f"INSERT INTO {KEYSPACE}.investigation_results (alert_id,generated_at,investigation_id,transaction_id,"
                "retrieved_context,retrieved_documents,retrieval_count,llm_explanation,investigation_summary,"
                "risk_reasoning,recommended_review_points,investigation_status,llm_model,rag_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            ),
        }

        tx_values = (
            ORIGIN, NOW, TRANSACTION_ID, date(NOW.year, NOW.month, NOW.day), NOW.hour,
            "PAYMENT", "CASSANDRA_TEST_DEST", 12.5, 20.0, 7.5, 0.0, 12.5,
            0.01, "L1", "ALLOW_STORE", 0.02, False, False,
            "smoke-test", "test-model", "cassandra-smoke-test", NOW,
        )
        alert_values = (
            ORIGIN, NOW, ALERT_ID, TRANSACTION_ID, date(NOW.year, NOW.month, NOW.day), NOW.hour,
            "TRANSFER", "CASSANDRA_TEST_DEST", 1000.0, 1500.0, 500.0, 0.0, 1000.0,
            0.2, "L5", "CRITICAL_INVESTIGATE", True, None, None, True,
            "smoke-test", "CRITICAL_INVESTIGATE", "test-model", "NEW", NOW,
        )
        investigation_values = (
            ALERT_ID, NOW, INVESTIGATION_ID, TRANSACTION_ID,
            "Synthetic smoke-test context", json.dumps([{"source": "smoke-test"}]), 1,
            "Synthetic smoke-test explanation", "Synthetic investigation", "Synthetic reasoning",
            json.dumps(["Review this synthetic record"]), "COMPLETED", "test-llm", "test-rag-v1",
        )

        try:
            session.execute(statements["transaction_insert"], tx_values)
            session.execute(statements["alert_insert"], alert_values)
            session.execute(statements["investigation_insert"], investigation_values)

            records = {
                "transactions": session.execute(
                    "SELECT * FROM transactions WHERE name_orig=%s AND event_time=%s AND transaction_id=%s",
                    (ORIGIN, NOW, TRANSACTION_ID),
                ).one(),
                "fraud_alerts": session.execute(
                    "SELECT * FROM fraud_alerts WHERE name_orig=%s AND event_time=%s AND alert_id=%s",
                    (ORIGIN, NOW, ALERT_ID),
                ).one(),
                "investigation_results": session.execute(
                    "SELECT * FROM investigation_results WHERE alert_id=%s AND generated_at=%s AND investigation_id=%s",
                    (ALERT_ID, NOW, INVESTIGATION_ID),
                ).one(),
            }
            for table, record in records.items():
                if record is None:
                    raise RuntimeError(f"Smoke-test read-back failed for {table}")
                print(f"{table}: {record._asdict()}")
        finally:
            session.execute(
                "DELETE FROM investigation_results WHERE alert_id=%s AND generated_at=%s AND investigation_id=%s",
                (ALERT_ID, NOW, INVESTIGATION_ID),
            )
            session.execute(
                "DELETE FROM fraud_alerts WHERE name_orig=%s AND event_time=%s AND alert_id=%s",
                (ORIGIN, NOW, ALERT_ID),
            )
            session.execute(
                "DELETE FROM transactions WHERE name_orig=%s AND event_time=%s AND transaction_id=%s",
                (ORIGIN, NOW, TRANSACTION_ID),
            )

        logger.info("Cassandra smoke test passed; synthetic rows were removed")
        return 0
    except Exception:
        logger.exception("Cassandra smoke test failed")
        return 1
    finally:
        close_connection(cluster, session)


if __name__ == "__main__":
    sys.exit(main())
