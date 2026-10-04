from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from . import config, monitoring
from .chat import AssistantUnavailable, answer_chat
from .runtime import Runtime
from .schemas import AssistantChatRequest, BatchRequest, ManualTransaction
from .storage import Store
from rag.investigation.llm_provider import verify_configured_chat_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger(__name__)


def batch_identifier() -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"BATCH-{date}-{uuid.uuid4().hex[:10].upper()}"


def _batch_progress(batch: dict) -> dict:
    requested = int(batch["requested_count"])
    batch["progress"] = min(100.0, round(100 * batch["generated_count"] / requested, 1)) if requested else 0.0
    return batch


def create_app(*, db_path: str | Path | None = None, start_workers: bool = True,
               producer=None) -> FastAPI:
    store = Store(db_path or config.sqlite_path())
    runtime_box: dict[str, Runtime] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.llm_provider_status = verify_configured_chat_provider()
        if not app.state.llm_provider_status.get("available", True):
            LOGGER.error(
                "Ask AI provider startup check failed provider=%s status=%s detail=%s",
                app.state.llm_provider_status.get("provider"),
                app.state.llm_provider_status.get("status"),
                app.state.llm_provider_status.get("detail", "provider is unavailable"),
            )
        runtime = Runtime(store, start_workers=start_workers, **({"producer": producer} if producer else {}))
        runtime_box["runtime"] = runtime
        app.state.runtime = runtime
        app.state.store = store
        yield
        runtime.close()

    app = FastAPI(title="Fraud Detection Control Center API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[config.FRONTEND_ORIGIN], allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Idempotency-Key"])
    app.mount("/metrics", make_asgi_app())

    def get_runtime() -> Runtime:
        value = runtime_box.get("runtime")
        if value is None:
            raise HTTPException(status_code=503, detail="Control Center is starting")
        return value

    @app.get("/api/health")
    def health():
        return {"status": "healthy", "service": "fraud-control-center-api", "time": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/dashboard")
    def dashboard():
        recent = store.batches(1)
        return {"summary": store.summary(), "current_batch": _batch_progress(recent[0]) if recent else None,
                "recent_batches": [_batch_progress(batch) for batch in store.batches(5)],
                "recent_transactions": store.list_transactions(page=1, page_size=8)["items"],
                "recent_activity": store.activity(limit=12)}

    @app.get("/api/system/status")
    def system_health():
        return monitoring.system_status(api_available=True)

    @app.get("/api/llm/status")
    def llm_status():
        return app.state.llm_provider_status

    @app.post("/api/llm/chat")
    def llm_chat(body: AssistantChatRequest):
        try:
            return answer_chat(body, store)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except AssistantUnavailable as exc:
            LOGGER.warning("Assistant request unavailable (%s)", str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from None

    @app.get("/api/llm/conversations/{conversation_id}")
    def llm_conversation(conversation_id: str):
        messages = store.chat_messages(conversation_id)
        if messages is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"conversation_id": conversation_id, "transaction_id": messages[0].get("transaction_id"),
                "message_count": len(messages), "messages": messages}

    @app.get("/api/llm/conversations/{conversation_id}/messages")
    def llm_conversation_messages(conversation_id: str):
        messages = store.chat_messages(conversation_id)
        if messages is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"conversation_id": conversation_id, "items": messages}

    @app.get("/api/monitoring/overview")
    def monitoring_overview():
        overview = monitoring.metrics_overview()
        overview["targets"] = monitoring.prometheus_targets()
        overview["grafana"] = monitoring.grafana_health()
        overview["grafana"]["dashboards"] = monitoring.grafana_dashboards()
        overview["alertmanager"] = monitoring.alertmanager_health()
        overview["links"] = {"prometheus": config.PROMETHEUS_URL, "grafana": config.GRAFANA_URL,
                              "alertmanager": config.ALERTMANAGER_URL}
        return overview

    @app.get("/api/monitoring/metrics")
    def monitoring_metrics(name: str | None = None):
        if name:
            if name not in monitoring.PROM_QUERIES:
                raise HTTPException(status_code=404, detail="Unknown or unsupported metric")
            return monitoring.metric(name)
        return {key: monitoring.metric(key) for key in monitoring.PROM_QUERIES}

    @app.get("/api/monitoring/prometheus/health")
    def monitoring_prometheus_health():
        return monitoring.prometheus_health()

    @app.get("/api/monitoring/prometheus/targets")
    def monitoring_targets():
        return monitoring.prometheus_targets()

    @app.get("/api/monitoring/grafana/health")
    def monitoring_grafana_health():
        return monitoring.grafana_health()

    @app.get("/api/monitoring/grafana/dashboards")
    def monitoring_dashboards():
        return monitoring.grafana_dashboards()

    @app.get("/api/monitoring/alertmanager/health")
    def monitoring_alertmanager_health():
        return monitoring.alertmanager_health()

    @app.get("/api/monitoring/links")
    def monitoring_links():
        return {"prometheus": config.PROMETHEUS_URL, "grafana": config.GRAFANA_URL,
                "alertmanager": config.ALERTMANAGER_URL}

    @app.get("/api/monitoring/alertmanager/alerts")
    def monitoring_alertmanager_alerts():
        try:
            import httpx
            response = httpx.get(f"{config.ALERTMANAGER_URL}/api/v2/alerts", timeout=2)
            response.raise_for_status()
            return {"available": True, "alerts": response.json()}
        except Exception as exc:
            return {"available": False, "alerts": [], "error": type(exc).__name__}

    @app.get("/api/batches")
    def list_batches(limit: int = Query(default=50, ge=1, le=100)):
        return {"items": [_batch_progress(item) for item in store.batches(limit)]}

    @app.post("/api/batches", status_code=202)
    def create_batch(body: BatchRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(status_code=400, detail="Idempotency-Key must contain 1 to 128 characters")
        canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        batch_id = batch_identifier()
        try:
            batch, created = store.create_batch(batch_id=batch_id, requested_count=body.count, delay=body.delay,
                source=body.source, idempotency_key=idempotency_key, request_hash=request_hash)
        except Exception:
            LOGGER.exception("Could not persist a Control Center batch")
            raise HTTPException(status_code=500, detail="Could not create batch")
        if not created:
            if batch["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different request")
            return _batch_progress(batch)
        from .runtime import BATCHES
        BATCHES.labels("queued", body.source).inc()
        runtime = get_runtime()
        runtime.emit(batch["batch_id"], "batch_queued")
        runtime.submit_batch(batch["batch_id"], body.count, body.delay, body.source)
        return _batch_progress(batch)

    @app.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str):
        batch = store.batch(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        return _batch_progress(batch)

    @app.post("/api/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str):
        batch = store.batch(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        if batch["status"] not in {"QUEUED", "RUNNING"} or not get_runtime().cancel(batch_id):
            raise HTTPException(status_code=409, detail="Batch is not currently cancellable")
        return _batch_progress(store.batch(batch_id))

    def transaction_filters(page: int, page_size: int, search: str | None, transaction_type: str | None,
                            risk_level: str | None, decision: str | None, kafka_status: str | None,
                            processing_status: str | None, investigation_status: str | None,
                            amount_min: float | None, amount_max: float | None, sort_by: str, sort_order: str,
                            batch_id: str | None = None):
        return store.list_transactions(batch_id=batch_id, page=page, page_size=page_size, search=search,
            transaction_type=transaction_type, risk_level=risk_level, decision=decision, kafka_status=kafka_status,
            processing_status=processing_status, investigation_status=investigation_status,
            amount_min=amount_min, amount_max=amount_max, sort_by=sort_by, sort_order=sort_order)

    @app.get("/api/batches/{batch_id}/transactions")
    def batch_transactions(batch_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                          search: str | None = None, transaction_type: str | None = None,
                          risk_level: str | None = None, decision: str | None = None,
                          kafka_status: str | None = None, processing_status: str | None = None,
                          investigation_status: str | None = None, amount_min: float | None = Query(None, ge=0),
                          amount_max: float | None = Query(None, ge=0), sort_by: str = "generated_at",
                          sort_order: str = "desc"):
        if not store.batch(batch_id):
            raise HTTPException(status_code=404, detail="Batch not found")
        return transaction_filters(page, page_size, search, transaction_type, risk_level, decision,
            kafka_status, processing_status, investigation_status, amount_min, amount_max, sort_by, sort_order, batch_id)

    @app.get("/api/transactions")
    def list_transactions(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                          search: str | None = None, transaction_type: str | None = None,
                          risk_level: str | None = None, decision: str | None = None,
                          kafka_status: str | None = None, processing_status: str | None = None,
                          investigation_status: str | None = None, amount_min: float | None = Query(None, ge=0),
                          amount_max: float | None = Query(None, ge=0), sort_by: str = "generated_at",
                          sort_order: str = "desc"):
        return transaction_filters(page, page_size, search, transaction_type, risk_level=risk_level, decision=decision,
            kafka_status=kafka_status, processing_status=processing_status, investigation_status=investigation_status,
            amount_min=amount_min, amount_max=amount_max, sort_by=sort_by, sort_order=sort_order,
            )

    @app.get("/api/transactions/{transaction_id}")
    def get_transaction(transaction_id: str):
        result = store.transaction(transaction_id)
        if not result:
            raise HTTPException(status_code=404, detail="Transaction not found in Control Center batches")
        return result

    @app.get("/api/transactions/{transaction_id}/investigation")
    def get_investigation(transaction_id: str):
        result = store.transaction(transaction_id)
        if not result:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if not result.get("alert_id"):
            raise HTTPException(status_code=404, detail="No fraud alert exists for this transaction")
        return {"status": result["investigation_status"], "alert_id": result["alert_id"],
                "investigation_id": result["investigation_id"], "result": result.get("investigation")}

    @app.get("/api/alerts")
    def list_alerts(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = None):
        return store.list_transactions(page=page, page_size=page_size, search=search, processing_status="FRAUD_ALERT")

    @app.get("/api/investigations")
    def list_investigations(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                            search: str | None = None, status: str | None = None):
        return store.list_transactions(page=page, page_size=page_size, search=search,
                                       investigation_status=status or "ALL")

    @app.get("/api/activity")
    def activity(batch_id: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return {"items": store.activity(batch_id=batch_id, limit=limit)}

    @app.post("/api/transactions", status_code=201)
    def send_transaction(body: ManualTransaction, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        if idempotency_key and len(idempotency_key) > 128:
            raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
        runtime = get_runtime()
        payload = body.kafka_payload()
        batch_id = batch_identifier()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        try:
            batch, created = store.create_batch(batch_id=batch_id, requested_count=1, delay=0,
                source="frontend_manual", idempotency_key=idempotency_key, request_hash=request_hash)
        except Exception:
            LOGGER.exception("Could not persist individual transaction request")
            raise HTTPException(status_code=500, detail="Could not create transaction request")
        if not created:
            if batch["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different transaction")
            tx = store.list_transactions(batch_id=batch["batch_id"], page=1, page_size=1)["items"]
            return {"batch": _batch_progress(batch), "transaction": tx[0] if tx else None, "replayed": True}
        # One manual transaction is small; wait only for its real Kafka acknowledgement.
        runtime._run_batch(batch_id, 1, 0, "frontend_manual", __import__("threading").Event(), [payload])
        result = store.list_transactions(batch_id=batch_id, page=1, page_size=1)["items"]
        batch = store.batch(batch_id)
        if not result or result[0]["kafka_status"] != "SENT":
            raise HTTPException(status_code=502, detail={"message": "Kafka did not acknowledge the transaction",
                                                        "batch": _batch_progress(batch),
                                                        "transaction": result[0] if result else None})
        return {"batch": _batch_progress(batch), "transaction": result[0], "replayed": False}

    @app.websocket("/ws/batches/{batch_id}")
    async def batch_socket(websocket: WebSocket, batch_id: str):
        if not store.batch(batch_id):
            await websocket.close(code=4404)
            return
        await websocket.accept()
        runtime = get_runtime()
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        entry = runtime.hub.subscribe(batch_id, asyncio.get_running_loop(), queue)
        await websocket.send_json({"type": "snapshot", "batch": _batch_progress(store.batch(batch_id))})
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "heartbeat", "at": time.time()})
        except WebSocketDisconnect:
            pass
        finally:
            runtime.hub.unsubscribe(batch_id, entry)

    return app


app = create_app()
