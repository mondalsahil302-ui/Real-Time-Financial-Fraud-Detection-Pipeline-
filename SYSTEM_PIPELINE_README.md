# Real‑Time Financial Fraud Detection Pipeline – System Overview

## Table of Contents
1. [Architecture Diagram](#architecture-diagram)
2. [Component Overview](#component-overview)
3. [Data Flow](#data-flow)
4. [Deployment & Runtime](#deployment--runtime)
5. [Running the System Locally](#running-the-system-locally)
6. [Key Configuration Files](#key-configuration-files)
7. [Testing & Validation](#testing--validation)
8. [Troubleshooting](#troubleshooting)
9. [Future Enhancements](#future-enhancements)

---

## Architecture Diagram
```mermaid
flowchart TD
    subgraph KafkaCluster[Kafka Cluster]
        K1[Kafka Topic: transactions]
        K2[Kafka Topic: alerts]
    end
    subgraph Spark[Spark Structured Streaming]
        S1[Driver] -->|Consume| K1
        S1 -->|Produce| K2
        S1 -->|Load Model| ModelWorker[Python Worker]
    end
    subgraph Model[Fraud Detection Models]
        M1[Isolation Forest (cached per worker)]
        M2[XGBoost (cached per worker)]
    end
    subgraph Storage[Storage Layer]
        C1[(Cassandra)]
        C2[(Object Store / Vector DB)]
    end
    subgraph RAG[Retrieval‑Augmented Generation]
        R1[Context Builder]
        R2[Orchestrator]
        R3[Gemini LLM Provider]
    end
    subgraph UI[Analyst Dashboard]
        UI1[React Front‑end]
    end
    
    K1 --> S1
    S1 --> ModelWorker
    ModelWorker --> M1 & M2
    ModelWorker --> C1
    ModelWorker --> R1
    R1 --> R2 --> R3
    R3 --> UI1
    K2 --> UI1
    C1 --> UI1
    C2 --> R1
```
*The diagram visualises the end‑to‑end flow from transaction ingestion to analyst assistance.*

---

## Component Overview
| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **Kafka** | Apache Kafka | Ingests raw transaction events (`transactions` topic) and publishes fraud alerts (`alerts` topic). |
| **Spark Structured Streaming** | Apache Spark (local[2] config) | Consumes transaction stream, performs feature engineering, and delegates scoring to Python workers. |
| **Python Workers** | Python (Spark `mapPartitions`) | Load heavy ML models **once per worker** (Isolation Forest, XGBoost) and compute **anomaly_score** = `-model.decision_function(X)`. |
| **Cassandra** | Apache Cassandra | Persists transaction details, model scores, and alert metadata for fast look‑ups. |
| **RAG Layer** | Custom Python (rag/ package) | Retrieves contextual information (PaySim cases, fraud knowledge base, regulatory snippets) and assembles a prompt for the LLM. |
| **Gemini LLM** | Google Gemini (gemini‑2.5‑flash) | Provides investigation explanations, answers analyst queries, and generates summary narratives. |
| **Frontend Dashboard** | React / Vite | Displays alerts, transaction details, and LLM‑generated explanations. |
| **Monitoring** | Prometheus + Grafana | Exposes Spark, Kafka, and LLM health metrics (`/metrics` endpoint). |

---

## Data Flow
1. **Transaction Ingestion** – Real‑time transactions are published to `kafka/topics/transactions`.
2. **Spark Driver** – Reads from Kafka, performs feature engineering (33‑feature contract) and forwards rows to a Python worker.
3. **Model Scoring (Worker‑local)** –
   - On first micro‑batch, the worker loads `models/isolation_forest_final.pkl` and `models/xgboost_final.pkl` into memory.
   - Scores each transaction, producing an `anomaly_score`.
4. **Persist & Alert** – Scores are written to Cassandra; if the score exceeds a dynamic threshold, an alert record is emitted to `kafka/topics/alerts`. 
5. **RAG Retrieval** – When an analyst clicks an alert, the backend assembles a context:
   - Transaction payload
   - Model outputs
   - Historical PaySim cases (retrieved from `rag_output/paysim_documents`)
   - Fraud knowledge base (`fraud_rag_knowledge_base/*.csv` – ignored in Git)
   - Regulatory snippets (optional)
6. **Gemini Explanation** – The assembled prompt is sent to the Gemini provider which returns a natural‑language explanation, investigation steps, and a concise summary.
7. **Dashboard Rendering** – The UI displays the alert together with the LLM‑generated narrative.

---

## Deployment & Runtime
- **Local Development** – Use `docker-compose.yml` which launches:
  - `kafka` (broker & Zookeeper)
  - `spark` (driver + workers)
  - `cassandra`
  - `prometheus` & `grafana`
  - `frontend`
- **Production** – Each component can be containerised individually; Spark can be scaled with more workers, and the LLM provider runs as a stateless FastAPI service (`backend/app`).
- **Configuration** – Environment variables are loaded from `.env`. Important keys:
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `CASSANDRA_CONTACT_POINTS`
  - `GEMINI_MODEL=gemini-2.5-flash`
  - `MODEL_PATH=./models/`

---

## Running the System Locally
```bash
# 1. Install dependencies (Python & Node)
conda create -n fraud-pipeline python=3.10 && conda activate fraud-pipeline
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 2. Start Docker services
docker-compose up -d

# 3. Verify services are healthy
curl http://localhost:8001/api/llm/status   # Should return Gemini ready
curl http://localhost:8002/metrics          # Prometheus metrics endpoint

# 4. Run Spark streaming job
python streaming/spark_streaming.py

# 5. Open the dashboard
open http://localhost:3000   # React UI
```
**Note:** The first run may take a minute for the ML models to be loaded and cached per worker.

---

## Key Configuration Files
- `.env` – Central environment configuration.
- `docker-compose.yml` – Service definitions.
- `backend/app/config.py` – FastAPI & LLM provider settings.
- `streaming/spark_worker_model.py` – Lazy model load implementation.
- `rag/metrics.py` – Prometheus metric definitions for the RAG subsystem.

---

## Testing & Validation
- **Unit Tests** – Run `pytest -q` to execute the full suite (`tests/`).
- **Integration Test** – `tools/test_full_pipeline.py` simulates a small Kafka stream and validates end‑to‑end alert creation and LLM response.
- **Performance** – Use `tools/evaluate_llm_providers.py` to compare response latency of Gemini vs fallback (Ollama removed). 

---

## Troubleshooting
| Symptom | Likely Cause | Fix |
|--------|--------------|-----|
| Spark crashes with `OutOfMemoryError` | Large model broadcast attempt | Ensure `spark_worker_model.py` loads model **locally**; remove any `sc.broadcast` of model files. |
| LLM returns fallback response | `.env` missing `GEMINI_API_KEY` or model unavailable | Verify API key and that `GEMINI_MODEL` is set correctly. |
| No alerts appear | Threshold configuration too high | Adjust `ALERT_THRESHOLD` in `backend/app/config.py` or tune Isolation Forest parameters. |
| Git push rejected (large file) | Accidentally added `fraud_rag_knowledge_base/*.csv` | Ensure `.gitignore` includes `fraud_rag_knowledge_base/*.csv`. |

---

## Future Enhancements
- **Streaming checkpointing** for exactly‑once semantics.
- **Model versioning** with MLflow and automatic rollout.
- **Dynamic LLM routing** – enable multiple providers if needed (e.g., Gemini + Claude). 
- **Alert enrichment** – integrate external threat‑intel APIs.
- **Scalable deployment** – Helm charts for Kubernetes.

---

*This README provides a comprehensive guide to understand, run, and extend the Real‑Time Financial Fraud Detection Pipeline.*

