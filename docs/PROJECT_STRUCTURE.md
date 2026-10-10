# Project Structure & Architecture Guide

**Project:** Real-Time Financial Fraud Detection Platform  
**Target Submission:** Academic Defense & Technical Demonstration  
**Author:** Software Project Architect & Lead ML Engineer  
**Date:** October 10, 2026  

---

## 1. Architectural Separation of Responsibilities

The platform is designed around strict separation of concerns across stream processing, statistical anomaly detection, supervised risk refinement, persistent state storage, context retrieval, and natural language explanation:

```text
Transaction Source (PaySim CSV / Simulator)
       │
       ▼
     Kafka (Topic: `transactions`)
       │
       ▼
Spark Structured Streaming (19 Base + 14 Behavioral Features = 33 Features)
       │
       ▼
Fraud Detection Models (Primary: Isolation Forest | Secondary: XGBoost)
       │
       ▼
Risk Score / Prediction / Decision (L1-L5 Risk Classification & Routing)
       │
       ├── Low-Risk (L1/L2) ───────────► Kafka: `low-risk-transactions`
       │                                          │
       └── High-Risk Alerts (L3/L4/L5) ──► Kafka: `fraud-alerts`
                                                  │
                                                  ▼
                                       Cassandra / State Storage
                                                  │
                                                  ▼
                                       RAG Evidence Retrieval (Chroma + Cassandra History)
                                                  │
                                                  ▼
                                       Gemini (Sole LLM: gemini-3.5-flash-lite)
                                                  │
                                                  ▼
                                       Investigation / Structured Explanation
                                                  │
                                                  ▼
                                       React Control Center Dashboard (Vite / Port 5173)
```

---

## 2. Directory Map & Component Responsibilities

```text
Real-Time-Financial-Fraud-Detection-Pipeline/
├── backend/                  FastAPI Control Center API, session store, LLM gateway
├── frontend/                 React / TypeScript / Vite operations console
├── producer/                 PaySim transaction ingestion & Kafka producer
├── streaming/                Spark Structured Streaming engine & real-time inference
├── models/                   Trained ML models (Isolation Forest, XGBoost) & feature contracts
├── database/                 Cassandra schema definitions, connection pools, and consumers
├── rag/                      RAG knowledge retrieval, vector database (Chroma), Gemini investigator
├── monitoring/               Prometheus alerting, Grafana dashboards, cAdvisor metrics
├── scripts/                  Orchestration, health validation, and launch scripts
├── tests/                    Comprehensive pytest & vitest test suites
├── tools/                    Diagnostic, benchmarking, and offline evaluation utilities
├── data/                     Authoritative PaySim transaction datasets
├── docs/                     System architecture, security audit, and runbook documentation
├── docker-compose.yml        Local infrastructure definition (Kafka, Cassandra, Prometheus, Grafana)
├── .env.example              Safe template for environment configuration
└── requirements.txt          Pinned Python dependencies
```

---

## 3. Verified Application Entry Points

| Subsystem | Exact Source File | Execution Entry Point | Default Network Port |
| :--- | :--- | :--- | :--- |
| **Control Center API** | `backend/app/main.py` | `uvicorn backend.app.main:app --port 8001` | `http://localhost:8001` |
| **Control Center UI** | `frontend/src/main.tsx` | `npm run dev` (from `frontend/`) | `http://localhost:5173` |
| **Kafka Producer** | `producer/producer.py` | `python -m producer.producer --max-transactions 50` | `http://localhost:8001` (metrics) |
| **Spark Streaming** | `streaming/spark_streaming.py` | `python streaming/spark_streaming.py` | `http://localhost:8002` (metrics) |
| **RAG Investigation**| `rag/investigation/kafka_investigation_consumer.py` | `python -m rag.investigation.kafka_investigation_consumer` | `http://localhost:8000` (metrics) |
| **One-Click Launcher**| `scripts/start_project.cmd` | `scripts\start_project.cmd` | Multi-process orchestration |
| **Demo 50 Pipeline** | `scripts/run_demo_50.cmd` | `scripts\run_demo_50.cmd` | Isolated end-to-end test |

---

## 4. Detailed Component Breakdown

### 4.1 Backend (`backend/`)
- **`backend/app/main.py`**: The primary FastAPI ASGI entry point. Exposes transaction query APIs, alert reviews, real-time batch simulator endpoints, and the LLM investigation gateway (`/api/llm/chat`, `/api/llm/status`). Hardened with global sanitized exception handlers and strict input validation constraints.
- **`backend/app/chat.py`**: Chat assistant orchestration integrating Google Gemini with RAG context grounding and prompt injection defenses.
- **`backend/app/schemas.py`**: Pydantic models defining input validation rules, transaction payloads, and response structures.
- **`backend/app/storage.py`**: Persistent SQLite storage layer (`control_center.sqlite3`) for transaction metadata, simulation history, and analyst review states. Uses parameterization and column whitelisting to eliminate SQL injection.
- **`backend/app/monitoring.py`**: Exposes Prometheus metrics and application health/readiness endpoints.

### 4.2 Frontend (`frontend/`)
- **`frontend/src/main.tsx` & `App.tsx`**: React 18 application shell built with Vite.
- **`frontend/src/AssistantPanel.tsx`**: AI Investigation Assistant interface rendering structured evidence, citations, and model reasoning from Gemini.
- **`frontend/src/TransactionDetail.tsx`**: Deep-dive transaction view showing feature-level anomaly indicators, balance errors, and ML risk scores.
- **`frontend/src/ManualTransactionForm.tsx`**: Interactive form allowing analysts to submit ad-hoc transactions for real-time scoring.
- **`frontend/src/api.ts`**: Centralized HTTP client enforcing disciplined API calls to `http://localhost:8001` with error resilience.

### 4.3 Streaming & ML Scoring (`streaming/` & `models/`)
- **`streaming/spark_streaming.py`**: Apache Spark Structured Streaming application consuming from Kafka `transactions`. Dynamically computes the full 33-feature contract (19 base features + 14 rolling account behavioral features) across micro-batches.
- **`streaming/spark_worker_model.py`**: Worker-level ML inference loader. Loads `models/isolation_forest_final.pkl` without Spark broadcast serialization overhead.
- **`models/`**: Contains trained model binaries and metadata:
  - `isolation_forest_final.pkl`: Primary unsupervised anomaly detector.
  - `isolation_forest_features.json`: Ordered 33-feature contract manifest.
  - `xgboost_second_stage.json`: Supervised classifier for secondary confirmation of borderline (L1/L2) transactions.

### 4.4 RAG & LLM Investigation (`rag/`)
- **`rag/investigation/llm_provider.py`**: Sole LLM connector implementing `gemini-3.5-flash-lite` via the Google Generative AI SDK. Implements bounded timeouts, exponential backoff, and JSON schema output enforcement.
- **`rag/investigation/llm_investigator.py`**: Builds the analytical context combining raw transaction attributes, historical account behavior, and retrieved domain knowledge.
- **`rag/investigation/kafka_investigation_consumer.py`**: Dedicated Kafka consumer reading from `fraud-alerts`. Enriches alerts with RAG context, invokes Gemini for automated narrative explanation, and commits results to Cassandra.
- **`rag/retrieval/`**: Multi-source context retrieval orchestrator:
  - `cassandra_retriever.py`: Retrieves historical transaction volume, velocity, and previous flags for `name_orig`.
  - `knowledge_retriever.py` & `paysim_retriever.py`: Semantic vector search against Chroma collections (`fraud_knowledge`, `paysim_cases`).

### 4.5 Data & Infrastructure Layer (`database/` & `docker-compose.yml`)
- **`database/schema.cql`**: Cassandra keyspace (`fraud_detection`) and table schema definitions:
  - `transactions`: Partitioned by `name_orig`, clustered by `step` and `transaction_id`.
  - `fraud_alerts`: Partitioned by `name_orig`, clustered by `created_at` and `alert_id`.
  - `investigation_results`: Keyed by `alert_id`.
- **`docker-compose.yml`**: Defines isolated service containers:
  - Kafka & Zookeeper: High-throughput event streaming.
  - Apache Cassandra: High-write operational storage.
  - Prometheus: Metric scraping and alert evaluation.
  - Grafana OSS: Interactive performance and fraud monitoring dashboards.

### 4.6 Verification & Diagnostics (`tests/` & `tools/`)
- **`tests/`**: Automated test suite containing 83+ tests across unit, API, schema, and integration levels. Features offline-aware skips to allow seamless verification without active Docker daemons.
- **`tools/`**: Offline evaluation scripts:
  - `test_llm_connection.py`: Verifies Gemini API key connectivity and model availability.
  - `test_llm_investigation.py`: Runs an offline RAG+LLM investigation against synthetic sample context without requiring live Kafka or Cassandra.
  - `health_check.py`: Complete pipeline health and port accessibility checker.

---

## 5. Architectural Integrity & Boundaries

1. **No Mixed Responsibilities:**
   - Spark Structured Streaming and scikit-learn/XGBoost are exclusively responsible for transaction scoring and routing decisions.
   - Google Gemini is strictly confined to post-detection investigation, explanation, evidence summarization, and human-in-the-loop analyst assistance. Gemini never overrides ML fraud scores or generates authoritative classifications.
2. **Deterministic Contracts:**
   - The 33-feature schema defined in `models/isolation_forest_features.json` is identical across training, streaming enrichment, batch simulation, and RAG context building.
3. **Data Protection:**
   - Operational secrets (`GEMINI_API_KEY`) remain strictly server-side and are never exposed to browser bundles or client responses.

