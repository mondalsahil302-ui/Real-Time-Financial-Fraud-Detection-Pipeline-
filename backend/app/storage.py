from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Small durable control-plane store; Kafka and Cassandra remain the pipeline data stores."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_count INTEGER NOT NULL,
                    generated_count INTEGER NOT NULL DEFAULT 0,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    delay REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                    sequence_number INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    kafka_status TEXT NOT NULL DEFAULT 'PENDING',
                    kafka_partition INTEGER,
                    kafka_offset INTEGER,
                    processing_status TEXT NOT NULL DEFAULT 'GENERATED',
                    risk_level TEXT,
                    anomaly_score REAL,
                    xgboost_probability REAL,
                    xgboost_prediction INTEGER,
                    final_prediction INTEGER,
                    decision_path TEXT,
                    final_decision TEXT,
                    alert_id TEXT,
                    investigation_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
                    investigation_id TEXT,
                    investigation_json TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(batch_id, sequence_number)
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_batch_sequence
                    ON transactions(batch_id, sequence_number);
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    conversation_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    transaction_id TEXT,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(conversation_id, sequence_number)
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_processing
                    ON transactions(processing_status, investigation_status);
                CREATE TABLE IF NOT EXISTS activity_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    transaction_id TEXT,
                    message TEXT NOT NULL,
                    data TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_activity_batch_event
                    ON activity_events(batch_id, event_id DESC);
            """)

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row else None

    def create_batch(self, *, batch_id: str, requested_count: int, delay: float,
                     source: str, idempotency_key: str | None, request_hash: str) -> tuple[dict, bool]:
        with self.connect() as con:
            try:
                con.execute("""INSERT INTO batches
                    (batch_id,idempotency_key,request_hash,status,requested_count,delay,source,created_at)
                    VALUES (?,?,?,'QUEUED',?,?,?,?)""",
                    (batch_id, idempotency_key, request_hash, requested_count, delay, source, now_iso()))
                row = con.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
                return dict(row), True
            except sqlite3.IntegrityError:
                if idempotency_key:
                    row = con.execute("SELECT * FROM batches WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                    if row:
                        return dict(row), False
                raise

    def batch(self, batch_id: str) -> dict | None:
        with self.connect() as con:
            row = self._dict(con.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone())
            if row:
                self._add_batch_counts(con, row)
            return row

    def batches(self, limit: int = 50) -> list[dict]:
        with self.connect() as con:
            result = [dict(row) for row in con.execute("SELECT * FROM batches ORDER BY created_at DESC LIMIT ?", (limit,))]
            for item in result:
                self._add_batch_counts(con, item)
            return result

    @staticmethod
    def _add_batch_counts(con: sqlite3.Connection, batch: dict) -> None:
        counts = con.execute("""SELECT
            SUM(CASE WHEN processing_status IN ('FRAUD_ALERT','LOW_RISK') THEN 1 ELSE 0 END) processed,
            SUM(CASE WHEN processing_status='FRAUD_ALERT' THEN 1 ELSE 0 END) fraud_alerts,
            SUM(CASE WHEN processing_status='LOW_RISK' THEN 1 ELSE 0 END) low_risk,
            SUM(CASE WHEN alert_id IS NOT NULL THEN 1 ELSE 0 END) investigation_requests,
            SUM(CASE WHEN investigation_status IN ('COMPLETED','PARTIAL','INSUFFICIENT_EVIDENCE') THEN 1 ELSE 0 END) investigations_completed,
            SUM(CASE WHEN investigation_status='COMPLETED' THEN 1 ELSE 0 END) investigations_succeeded,
            SUM(CASE WHEN investigation_status IN ('PARTIAL','INSUFFICIENT_EVIDENCE') THEN 1 ELSE 0 END) investigations_partial,
            SUM(CASE WHEN investigation_status='PENDING' AND alert_id IS NOT NULL THEN 1 ELSE 0 END) investigations_pending,
            SUM(CASE WHEN investigation_status='FAILED' THEN 1 ELSE 0 END) investigations_failed
            FROM transactions WHERE batch_id=?""", (batch["batch_id"],)).fetchone()
        batch.update({key: int(counts[key] or 0) for key in counts.keys()})

    def start_batch(self, batch_id: str) -> None:
        with self.connect() as con:
            con.execute("UPDATE batches SET status='RUNNING', started_at=? WHERE batch_id=? AND status='QUEUED'", (now_iso(), batch_id))

    def _event(self, con: sqlite3.Connection, batch_id: str, event_type: str,
               message: str, transaction_id: str | None = None, data: dict | None = None) -> None:
        con.execute("INSERT INTO activity_events(batch_id,created_at,event_type,transaction_id,message,data) VALUES(?,?,?,?,?,?)",
                    (batch_id, now_iso(), event_type, transaction_id, message, json.dumps(data or {}, ensure_ascii=False)))
        con.execute("DELETE FROM activity_events WHERE event_id NOT IN (SELECT event_id FROM activity_events ORDER BY event_id DESC LIMIT 10000)")

    def generated(self, batch_id: str, sequence: int, payload: dict) -> dict:
        txid = str(payload["transaction_id"])
        with self.connect() as con:
            con.execute("""INSERT INTO transactions(transaction_id,batch_id,sequence_number,payload,generated_at,updated_at)
                         VALUES(?,?,?,?,?,?)""", (txid, batch_id, sequence, json.dumps(payload, ensure_ascii=False),
                         payload["event_time"], now_iso()))
            con.execute("UPDATE batches SET generated_count=generated_count+1 WHERE batch_id=?", (batch_id,))
            self._event(con, batch_id, "transaction_generated", "Transaction generated", txid,
                        {"sequence_number": sequence})
        return self.transaction(txid)  # type: ignore[return-value]

    def sent(self, transaction_id: str, partition: int | None, offset: int | None) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT batch_id FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
            if not row:
                return None
            batch_id = row["batch_id"]
            con.execute("UPDATE transactions SET kafka_status='SENT',kafka_partition=?,kafka_offset=?,updated_at=? WHERE transaction_id=?",
                        (partition, offset, now_iso(), transaction_id))
            con.execute("UPDATE batches SET sent_count=sent_count+1 WHERE batch_id=?", (batch_id,))
            self._event(con, batch_id, "transaction_sent", "Kafka acknowledged transaction", transaction_id,
                        {"partition": partition, "offset": offset})
        return self.transaction(transaction_id)

    def failed(self, batch_id: str, transaction_id: str | None, error: str) -> None:
        with self.connect() as con:
            if transaction_id:
                con.execute("UPDATE transactions SET kafka_status='FAILED',processing_status='FAILED',updated_at=? WHERE transaction_id=?",
                            (now_iso(), transaction_id))
            con.execute("UPDATE batches SET failed_count=failed_count+1,error_message=? WHERE batch_id=?", (error[:500], batch_id))
            self._event(con, batch_id, "transaction_failed", "Kafka send failed", transaction_id, {"error": error[:250]})

    def finish_batch(self, batch_id: str, *, cancelled: bool = False, error: str | None = None) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            if not row:
                return None
            if cancelled:
                status = "CANCELLED"
            elif row["sent_count"] == row["requested_count"] and row["failed_count"] == 0:
                status = "COMPLETED"
            elif row["sent_count"] > 0:
                status = "PARTIAL"
            elif error or row["failed_count"]:
                status = "FAILED"
            else:
                status = "FAILED"
            message = (error or row["error_message"])
            con.execute("UPDATE batches SET status=?,completed_at=?,error_message=COALESCE(?,error_message) WHERE batch_id=?",
                        (status, now_iso(), message[:500] if message else None, batch_id))
            self._event(con, batch_id, "batch_completed", f"Batch {status.lower()}", data={"status": status})
        return self.batch(batch_id)

    def transaction(self, transaction_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
        return self._expand_transaction(row)

    @staticmethod
    def _expand_transaction(row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        if value.get("investigation_json"):
            value["investigation"] = json.loads(value["investigation_json"])
        else:
            value["investigation"] = None
        return value

    def list_transactions(self, *, batch_id: str | None = None, page: int = 1, page_size: int = 25,
                          search: str | None = None, transaction_type: str | None = None,
                          risk_level: str | None = None, decision: str | None = None,
                          kafka_status: str | None = None, processing_status: str | None = None,
                          investigation_status: str | None = None, amount_min: float | None = None,
                          amount_max: float | None = None, sort_by: str = "generated_at", sort_order: str = "desc") -> dict:
        clauses, values = [], []
        if batch_id:
            clauses.append("batch_id=?"); values.append(batch_id)
        if search:
            needle = f"%{search}%"
            clauses.append("(transaction_id LIKE ? OR json_extract(payload,'$.nameOrig') LIKE ? OR json_extract(payload,'$.nameDest') LIKE ?)")
            values.extend((needle, needle, needle))
        if transaction_type:
            clauses.append("json_extract(payload,'$.type')=?"); values.append(transaction_type)
        if risk_level:
            clauses.append("risk_level=?"); values.append(risk_level)
        if decision:
            clauses.append("final_decision=?"); values.append(decision)
        if kafka_status:
            clauses.append("kafka_status=?"); values.append(kafka_status)
        if processing_status:
            clauses.append("processing_status=?"); values.append(processing_status)
        if investigation_status == "ALL":
            clauses.append("alert_id IS NOT NULL")
        elif investigation_status:
            clauses.append("investigation_status=?"); values.append(investigation_status)
        if amount_min is not None:
            clauses.append("CAST(json_extract(payload,'$.amount') AS REAL)>=?"); values.append(amount_min)
        if amount_max is not None:
            clauses.append("CAST(json_extract(payload,'$.amount') AS REAL)<=?"); values.append(amount_max)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sort_columns = {"generated_at": "generated_at", "amount": "CAST(json_extract(payload,'$.amount') AS REAL)", "type": "json_extract(payload,'$.type')", "risk_level": "risk_level"}
        order = "ASC" if sort_order.lower() == "asc" else "DESC"
        sort = sort_columns.get(sort_by, "generated_at")
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM transactions" + where, values).fetchone()[0]
            rows = con.execute(f"SELECT * FROM transactions{where} ORDER BY {sort} {order}, sequence_number ASC LIMIT ? OFFSET ?",
                               [*values, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [self._expand_transaction(row) for row in rows], "page": page, "page_size": page_size, "total": total}

    def record_decision(self, payload: dict, decision_topic: str) -> dict | None:
        txid = str(payload.get("transaction_id", ""))
        if not txid:
            return None
        alert = decision_topic == "fraud"
        alert_id = payload.get("alert_id")
        if alert and not alert_id:
            import uuid
            # Matches database.fraud_alert_consumer.build_row's persisted primary key.
            alert_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fraud-alert:{txid}"))
        final_decision = payload.get("final_risk_action") or ("FRAUD_ALERT" if alert else "LOW_RISK")
        with self.connect() as con:
            row = con.execute("SELECT batch_id FROM transactions WHERE transaction_id=?", (txid,)).fetchone()
            if not row:
                return None
            batch_id = row["batch_id"]
            con.execute("""UPDATE transactions SET processing_status=?,risk_level=?,anomaly_score=?,
                xgboost_probability=?,xgboost_prediction=?,final_prediction=?,decision_path=?,final_decision=?,
                alert_id=?,investigation_status=?,updated_at=? WHERE transaction_id=?""",
                ("FRAUD_ALERT" if alert else "LOW_RISK", payload.get("risk_level"), payload.get("anomaly_score"),
                 payload.get("xgboost_probability"), payload.get("xgboost_prediction"), payload.get("final_prediction"),
                 payload.get("final_decision_path"), final_decision, alert_id,
                 "PENDING" if alert else "NOT_APPLICABLE", now_iso(), txid))
            self._event(con, batch_id, "fraud_alert" if alert else "low_risk",
                        "Pipeline produced fraud alert" if alert else "Pipeline classified low risk", txid,
                        {"risk_level": payload.get("risk_level"), "decision": final_decision})
        return self.transaction(txid)

    def update_investigation(self, transaction_id: str, investigation: dict) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT batch_id FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
            if not row:
                return None
            batch_id = row["batch_id"]
            status = str(investigation.get("investigation_status", "failed")).upper()
            con.execute("UPDATE transactions SET investigation_status=?,investigation_id=?,investigation_json=?,updated_at=? WHERE transaction_id=?",
                        (status, investigation.get("investigation_id"), json.dumps(investigation, ensure_ascii=False), now_iso(), transaction_id))
            self._event(con, batch_id, "investigation_completed", "Investigation status updated", transaction_id,
                        {"status": status, "investigation_id": investigation.get("investigation_id")})
        return self.transaction(transaction_id)

    def pending_investigations(self, limit: int = 50) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT transaction_id,alert_id FROM transactions WHERE alert_id IS NOT NULL AND investigation_status='PENDING' LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def activity(self, batch_id: str | None = None, limit: int = 100) -> list[dict]:
        with self.connect() as con:
            if batch_id:
                rows = con.execute("SELECT * FROM activity_events WHERE batch_id=? ORDER BY event_id DESC LIMIT ?", (batch_id, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM activity_events ORDER BY event_id DESC LIMIT ?", (limit,)).fetchall()
        result = [dict(row) for row in rows]
        for item in result:
            item["data"] = json.loads(item["data"])
        return result

    def summary(self) -> dict:
        with self.connect() as con:
            batch_rows = con.execute("SELECT COALESCE(SUM(requested_count),0) requested,COALESCE(SUM(generated_count),0) generated,COALESCE(SUM(sent_count),0) sent,COALESCE(SUM(failed_count),0) failed FROM batches").fetchone()
            tx_rows = con.execute("""SELECT COUNT(*) processed,
                SUM(CASE WHEN processing_status='FRAUD_ALERT' THEN 1 ELSE 0 END) fraud_alerts,
                SUM(CASE WHEN processing_status='LOW_RISK' THEN 1 ELSE 0 END) low_risk,
                SUM(CASE WHEN alert_id IS NOT NULL THEN 1 ELSE 0 END) investigations,
                SUM(CASE WHEN investigation_status='PENDING' AND alert_id IS NOT NULL THEN 1 ELSE 0 END) investigation_pending,
                SUM(CASE WHEN investigation_status IN ('COMPLETED','PARTIAL','INSUFFICIENT_EVIDENCE') THEN 1 ELSE 0 END) investigation_success,
                SUM(CASE WHEN investigation_status='FAILED' THEN 1 ELSE 0 END) investigation_failed
                FROM transactions WHERE processing_status IN ('FRAUD_ALERT','LOW_RISK')""").fetchone()
        return {key: int(batch_rows[key] or 0) for key in batch_rows.keys()} | {key: int(tx_rows[key] or 0) for key in tx_rows.keys()}

    def chat_messages(self, conversation_id: str) -> list[dict] | None:
        with self.connect() as con:
            rows = con.execute("SELECT transaction_id,role,content,created_at FROM assistant_messages WHERE conversation_id=? ORDER BY sequence_number",
                               (conversation_id,)).fetchall()
        return ([dict(row) for row in rows] if rows else None)

    def save_chat_message(self, conversation_id: str, transaction_id: str | None, role: str, content: str) -> None:
        with self.connect() as con:
            sequence = con.execute("SELECT COALESCE(MAX(sequence_number),0)+1 FROM assistant_messages WHERE conversation_id=?",
                                   (conversation_id,)).fetchone()[0]
            con.execute("INSERT INTO assistant_messages(conversation_id,sequence_number,transaction_id,role,content,created_at) VALUES(?,?,?,?,?,?)",
                        (conversation_id, sequence, transaction_id, role, content, now_iso()))

    def events_for_batch(self, batch_id: str, limit: int = 200) -> list[dict]:
        return self.activity(batch_id=batch_id, limit=limit)
