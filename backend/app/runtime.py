from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter, Histogram

from producer.producer import produce_batch as run_existing_producer

from . import config
from .storage import Store

LOGGER = logging.getLogger(__name__)

BATCHES = Counter("simulation_batches_total", "Control Center batches by outcome", ("status", "source"))
BATCHES_STARTED = Counter("simulation_batches_started_total", "Control Center batches started", ("source",))
BATCHES_COMPLETED = Counter("simulation_batches_completed_total", "Control Center batches completed", ("source",))
BATCHES_FAILED = Counter("simulation_batches_failed_total", "Control Center batches that failed", ("source",))
TRANSACTIONS_GENERATED = Counter("simulation_transactions_generated_total", "Generated transactions", ("source",))
TRANSACTIONS_SENT = Counter("simulation_transactions_sent_total", "Kafka acknowledged transactions", ("source",))
TRANSACTIONS_FAILED = Counter("simulation_transactions_failed_total", "Failed Kafka sends", ("source",))
GENERATION_DURATION = Histogram("simulation_generation_duration_seconds", "Batch generation duration", ("source",))
SEND_DURATION = Histogram("simulation_transaction_send_duration_seconds", "Transaction send duration", ("source",))


class EventHub:
    """Fan out real state changes to batch WebSockets, with bounded per-client queues."""
    def __init__(self):
        self._subscribers: dict[str, set[tuple[Any, Any]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, batch_id: str, loop, queue):
        entry = (loop, queue)
        with self._lock:
            self._subscribers.setdefault(batch_id, set()).add(entry)
        return entry

    def unsubscribe(self, batch_id: str, entry) -> None:
        with self._lock:
            group = self._subscribers.get(batch_id)
            if group:
                group.discard(entry)
                if not group:
                    self._subscribers.pop(batch_id, None)

    def publish(self, batch_id: str, event: dict) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(batch_id, ()))
        for loop, queue in subscribers:
            def enqueue(q=queue, value=event):
                if q.full():
                    try:
                        q.get_nowait()
                    except Exception:
                        pass
                q.put_nowait(value)
            try:
                loop.call_soon_threadsafe(enqueue)
            except RuntimeError:
                pass


class Runtime:
    def __init__(self, store: Store, *, start_workers: bool = True, producer=run_existing_producer):
        self.store = store
        self.hub = EventHub()
        self.producer = producer
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="control-center-batch")
        self.cancel_events: dict[str, threading.Event] = {}
        self.pending_send_time: dict[str, float] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.workers: list[threading.Thread] = []
        if start_workers:
            for topic, kind in ((config.FRAUD_ALERTS_TOPIC, "fraud"), (config.LOW_RISK_TOPIC, "low_risk")):
                thread = threading.Thread(target=self._decision_worker, args=(topic, kind), daemon=True,
                                          name=f"control-center-{kind}-events")
                thread.start()
                self.workers.append(thread)
            poller = threading.Thread(target=self._investigation_worker, daemon=True, name="control-center-investigations")
            poller.start()
            self.workers.append(poller)

    def close(self) -> None:
        self.stop_event.set()
        with self.lock:
            for flag in self.cancel_events.values():
                flag.set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def emit(self, batch_id: str, event_type: str, *, transaction: dict | None = None, extra: dict | None = None) -> None:
        batch = self.store.batch(batch_id)
        self.hub.publish(batch_id, {"type": event_type, "batch": batch,
                                    "transaction": transaction, "data": extra or {}, "at": time.time()})

    def submit_batch(self, batch_id: str, count: int, delay: float, source: str = "frontend_simulator") -> None:
        cancel = threading.Event()
        with self.lock:
            self.cancel_events[batch_id] = cancel
        self.pool.submit(self._run_batch, batch_id, count, delay, source, cancel, None)

    def submit_manual(self, batch_id: str, payload: dict, source: str = "frontend_manual") -> None:
        cancel = threading.Event()
        with self.lock:
            self.cancel_events[batch_id] = cancel
        self.pool.submit(self._run_batch, batch_id, 1, 0.0, source, cancel, [payload])

    def cancel(self, batch_id: str) -> bool:
        with self.lock:
            cancel = self.cancel_events.get(batch_id)
        if not cancel or cancel.is_set():
            return False
        cancel.set()
        self.emit(batch_id, "batch_cancellation_requested")
        return True

    def _run_batch(self, batch_id: str, count: int, delay: float, source: str,
                   cancel: threading.Event, transactions: list[dict] | None) -> None:
        started = time.perf_counter()
        self.store.start_batch(batch_id)
        BATCHES_STARTED.labels(source).inc()
        BATCHES.labels("running", source).inc()
        self.emit(batch_id, "batch_started")
        errors: list[str] = []

        def generated(payload: dict, sequence: int) -> None:
            row = self.store.generated(batch_id, sequence, payload)
            self.pending_send_time[payload["transaction_id"]] = time.perf_counter()
            TRANSACTIONS_GENERATED.labels(source).inc()
            self.emit(batch_id, "transaction_generated", transaction=row)

        def sent(payload: dict, metadata) -> None:
            transaction_id = payload["transaction_id"]
            start = self.pending_send_time.pop(transaction_id, time.perf_counter())
            SEND_DURATION.labels(source).observe(time.perf_counter() - start)
            TRANSACTIONS_SENT.labels(source).inc()
            row = self.store.sent(transaction_id, getattr(metadata, "partition", None), getattr(metadata, "offset", None))
            self.emit(batch_id, "transaction_sent", transaction=row)

        def failed(payload: dict | None, error: Exception) -> None:
            message = f"{type(error).__name__}: {error}"
            errors.append(message)
            TRANSACTIONS_FAILED.labels(source).inc()
            txid = payload.get("transaction_id") if payload else None
            self.pending_send_time.pop(txid, None) if txid else None
            self.store.failed(batch_id, txid, message)
            self.emit(batch_id, "transaction_failed", transaction=self.store.transaction(txid) if txid else None,
                      extra={"error": message[:250]})

        try:
            result = self.producer(count, delay, source=source, batch_id=batch_id, transactions=transactions,
                                   cancel_event=cancel, on_generated=generated, on_sent=sent,
                                   on_failed=failed, serve_metrics=False, continue_on_error=True)
            ended = self.store.finish_batch(batch_id, cancelled=result.cancelled or cancel.is_set(),
                                            error=errors[0] if errors else None)
            status = str((ended or {}).get("status", "FAILED")).lower()
            BATCHES.labels(status, source).inc()
            if status == "completed":
                BATCHES_COMPLETED.labels(source).inc()
            if status in {"failed", "partial"}:
                BATCHES_FAILED.labels(source).inc()
            self.emit(batch_id, "batch_completed", extra={"duration_seconds": time.perf_counter() - started})
        except Exception as exc:
            LOGGER.exception("Control Center batch %s failed", batch_id)
            ended = self.store.finish_batch(batch_id, cancelled=cancel.is_set(), error=f"{type(exc).__name__}: {exc}")
            status = str((ended or {}).get("status", "FAILED")).lower()
            BATCHES.labels(status, source).inc()
            BATCHES_FAILED.labels(source).inc()
            self.emit(batch_id, "batch_failed", extra={"error": type(exc).__name__})
        finally:
            GENERATION_DURATION.labels(source).observe(time.perf_counter() - started)
            with self.lock:
                self.cancel_events.pop(batch_id, None)

    def _decision_worker(self, topic: str, kind: str) -> None:
        group = f"fraud-control-center-{kind}"
        while not self.stop_event.is_set():
            consumer = None
            try:
                from kafka import KafkaConsumer
                consumer = KafkaConsumer(topic, bootstrap_servers=config.KAFKA_SERVERS.split(","),
                    group_id=group, enable_auto_commit=True, auto_offset_reset="latest",
                    value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
                    consumer_timeout_ms=1000, max_poll_records=100,
                    client_id=f"{group}-observer")
                LOGGER.info("Control Center observing Kafka topic %s with independent group %s", topic, group)
                while not self.stop_event.is_set():
                    records = consumer.poll(timeout_ms=750, max_records=100)
                    for messages in records.values():
                        for message in messages:
                            payload = message.value
                            if not isinstance(payload, dict):
                                continue
                            row = self.store.record_decision(payload, kind)
                            if row:
                                self.emit(row["batch_id"], "fraud_alert" if kind == "fraud" else "low_risk",
                                          transaction=row)
            except Exception as exc:
                if not self.stop_event.is_set():
                    LOGGER.warning("Control Center Kafka observer for %s unavailable (%s); retrying", topic, type(exc).__name__)
                    self.stop_event.wait(3)
            finally:
                if consumer:
                    try:
                        consumer.close(autocommit=False)
                    except Exception:
                        pass

    def _investigation_worker(self) -> None:
        while not self.stop_event.is_set():
            pending = self.store.pending_investigations(30)
            if not pending:
                self.stop_event.wait(3)
                continue
            cluster = session = None
            try:
                from database.cassandra_connection import close_connection, get_cassandra_config, get_session
                cluster, session = get_session()
                keyspace = get_cassandra_config().keyspace
                statement = session.prepare(f"SELECT investigation_id,generated_at,llm_explanation,investigation_status,llm_model,rag_version FROM {keyspace}.investigation_results WHERE alert_id=? LIMIT 1")
                for item in pending:
                    if self.stop_event.is_set():
                        break
                    row = session.execute(statement, (item["alert_id"],), timeout=2).one()
                    if row:
                        raw = getattr(row, "llm_explanation", None)
                        try:
                            investigation = json.loads(raw) if raw else {}
                        except (TypeError, json.JSONDecodeError):
                            investigation = {"investigation_summary": getattr(row, "investigation_summary", None)}
                        investigation.setdefault("investigation_id", getattr(row, "investigation_id", None))
                        investigation.setdefault("alert_id", item["alert_id"])
                        investigation.setdefault("investigation_status", getattr(row, "investigation_status", "failed"))
                        investigation.setdefault("llm_model", getattr(row, "llm_model", None))
                        investigation.setdefault("rag_version", getattr(row, "rag_version", None))
                        updated = self.store.update_investigation(item["transaction_id"], investigation)
                        if updated:
                            self.emit(updated["batch_id"], "investigation_completed", transaction=updated)
            except Exception as exc:
                if not self.stop_event.is_set():
                    LOGGER.warning("Control Center Cassandra investigation lookup unavailable (%s)", type(exc).__name__)
            finally:
                if cluster and session:
                    try:
                        close_connection(cluster, session)
                    except Exception:
                        pass
            self.stop_event.wait(3)
