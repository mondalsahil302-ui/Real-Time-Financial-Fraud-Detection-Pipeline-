# Production Deployment & Containerization Guide

**Project:** Real-Time Financial Fraud Detection Platform  
**Target Audience:** Enterprise DevOps, Site Reliability Engineers (SRE), and Technical Evaluators  
**Version:** 1.0.0 (Company Submission-Ready)  
**Date:** October 2026  

---

## 1. Executive Summary

This document details the production containerization, deployment architecture, resource requirements, and operational maintenance procedures for the **Real-Time Financial Fraud Detection Platform**. 

The platform runs as a coordinated, microservice-oriented Docker Compose stack containing event streaming (Apache Kafka), persistent distributed storage (Apache Cassandra), real-time machine learning inference (Isolation Forest + XGBoost), context retrieval (Chroma Vector DB), generative artificial intelligence investigation (Google Gemini 3.5 Flash Lite), an enterprise ASGI Control Center (FastAPI), and a modern React 18 / Nginx web console.

---

## 2. Service Architecture & Port Matrix

| Service | Container Name | Image / Tag | Internal Port | Host Port | Purpose | Healthcheck Endpoint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Control Center UI** | `fraud-frontend` | `fraud-detection-frontend:1.0.0` | `80/tcp` | `5173:80` | Production React SPA served via Nginx | `wget -q --spider http://127.0.0.1:80/` |
| **Control Center API**| `fraud-backend` | `fraud-detection-api:1.0.0` | `8001/tcp` | `8001:8001` | FastAPI REST & WebSocket server | `curl -f http://127.0.0.1:8001/api/health` |
| **Kafka Broker** | `fraud-kafka` | `apache/kafka:4.3.1` | `9092/tcp` | `9092:9092` | Event streaming backbone | `kafka-topics.sh --list` |
| **Cassandra DB** | `fraud-cassandra`| `cassandra:5.0.9` | `9042/tcp` | `9042:9042` | Operational account & alert storage | `cqlsh -e 'DESCRIBE KEYSPACES'` |
| **Prometheus** | `fraud-prometheus` | `prom/prometheus:v3.15.0` | `9090/tcp` | `9090:9090` | Time-series metric collection | `wget -q -O- http://localhost:9090/-/healthy` |
| **Grafana OSS** | `fraud-grafana` | `grafana/grafana:13.2.3` | `3000/tcp` | `3000:3000` | Pre-provisioned dashboards | `wget -q -O- http://localhost:3000/api/health` |
| **Alertmanager** | `fraud-alertmanager`| `prom/alertmanager:v0.28.1`| `9093/tcp` | `9093:9093` | Alert routing & notification rules | `wget -q -O- http://localhost:9093/-/healthy` |
| **cAdvisor** | `fraud-cadvisor` | `gcr.io/cadvisor/cadvisor:v0.52.1`| `8080/tcp` | `8080:8080` | Container resource telemetry | Process health |

---

## 3. Production Container Images

### 3.1 Backend Application Image (`fraud-detection-api:1.0.0`)
- **Base Image:** `python:3.11-slim` (Multi-stage build)
- **Security:** Runs as non-root user `appuser:appgroup` (UID/GID 1000). No build compilers or package managers remain in runtime layers.
- **Pre-Loaded Artifacts:**
  - `models/isolation_forest_final.pkl` (33-feature unsupervised anomaly detector)
  - `models/xgboost_second_stage.json` (Supervised cascade classifier)
  - `models/isolation_forest_features.json` (Deterministic feature contract)
  - `fraud_rag_knowledge_base/` (Authoritative financial crime typologies and regulatory guidelines)
- **Signal Handling:** Uvicorn handles `SIGTERM` and `SIGINT` gracefully for zero-downtime rolling deploys.
- **Build Command:**
  ```bash
  docker build -t fraud-detection-api:1.0.0 .
  ```

### 3.2 Frontend Web Console Image (`fraud-detection-frontend:1.0.0`)
- **Stage 1 (Builder):** `node:20-alpine` compiling TypeScript (`tsc -b`) and Vite production bundle.
- **Stage 2 (Runtime):** `nginx:1.27-alpine` (Minimal size ~21MB).
- **Reverse Proxy:** Forwards `/api/` to `http://backend:8001/api/` and `/ws` to `http://backend:8001/ws` with WebSocket upgrade headers.
- **SPA Fallback:** Implements `try_files $uri $uri/ /index.html;` to support direct browser navigation across React routes.
- **Build Command:**
  ```bash
  docker build -f docker/Dockerfile.frontend -t fraud-detection-frontend:1.0.0 .
  ```

---

## 4. Environment Configuration (`.env`)

Create your local `.env` from the provided template:

```bash
cp .env.example .env
```

### Essential Production Variables

```ini
# Google Gemini LLM Credentials (Server-Side Only)
GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here...
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=60

# Distributed Data Services
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
CASSANDRA_HOST=localhost
CASSANDRA_PORT=9042
CASSANDRA_KEYSPACE=fraud_detection

# Observability Infrastructure
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
ALERTMANAGER_URL=http://localhost:9093
```

> [!WARNING]
> Never commit `.env` to Git. The project `.gitignore` and `.dockerignore` strictly prevent credentials from entering images or version control.

---

## 5. Deployment Procedures

### 5.1 One-Command Full Stack Startup
From the repository root:

```bash
# 1. Build all application images
docker compose build

# 2. Launch the entire containerized pipeline in the background
docker compose up -d

# 3. Verify service health and running state
docker compose ps
```

### 5.2 Verification of Stack Health
Execute the automated health and readiness check:

```bash
# Check Docker container status
docker compose ps

# Check FastAPI health endpoint
curl -f http://localhost:8001/api/health

# Check Gemini LLM readiness
curl -f http://localhost:8001/api/llm/status
```

*Expected response from `/api/llm/status`:*
```json
{
  "provider": "gemini",
  "model": "gemini-3.5-flash-lite",
  "status": "ready",
  "available": true,
  "rag_enabled": true,
  "fallback": "none"
}
```

---

## 6. Accessing Platform Dashboards

| Service | Access URL | Credentials | Notes |
| :--- | :--- | :--- | :--- |
| **Fraud Control Center** | [http://localhost:5173](http://localhost:5173) | None | Full analyst UI (Simulator, Alerts, Assistant) |
| **FastAPI Swagger Docs** | [http://localhost:8001/docs](http://localhost:8001/docs) | None | Interactive OpenAPI specification |
| **Grafana Dashboards** | [http://localhost:3000](http://localhost:3000) | `admin` / `admin` | 6 pre-provisioned telemetry dashboards |
| **Prometheus Console** | [http://localhost:9090](http://localhost:9090) | None | Metric query and target status interface |
| **Alertmanager UI** | [http://localhost:9093](http://localhost:9093) | None | Pipeline failure and latency alert manager |

---

## 7. Data Persistence & Volume Management

The platform utilizes named Docker volumes to guarantee that databases and state survive container upgrades and restarts:

| Volume Name | Target Container Path | Content Preserved |
| :--- | :--- | :--- |
| `cassandra_data` | `/var/lib/cassandra` | Transaction history, fraud alerts, Cassandra investigations |
| `kafka_data` | `/var/lib/kafka/data` | Kafka partition logs for `transactions` and `fraud-alerts` |
| `backend_data` | `/app/backend/data` | Control Center SQLite state (`control_center.sqlite3`) |
| `vector_db_data` | `/app/vector_db` | Chroma embeddings for fraud typologies and cases |
| `prometheus_data` | `/prometheus` | Time-series metrics and historical scrape data |
| `grafana_data` | `/var/lib/grafana` | User dashboards, alert rules, and preferences |
| `alertmanager_data`| `/alertmanager` | Alert notification silence state |

### Safe Teardown (Preserving Data)
```bash
docker compose down
```

> [!CAUTION]
> Do NOT pass `-v` or `--volumes` to `docker compose down` unless you explicitly want to purge all historical transactions, alerts, and database state.

---

## 8. Recommended Hardware & System Sizing

| Metric | Minimum (Local Evaluation) | Recommended (Production Staging) |
| :--- | :--- | :--- |
| **Host CPU** | 4 Cores (x86_64) | 8+ Cores |
| **Host RAM** | 8 GB RAM | 16 GB RAM |
| **Disk Space** | 20 GB Free SSD | 100 GB Free NVMe SSD |
| **OS** | Windows 10/11 with WSL2, Ubuntu 22.04 LTS, or macOS (Apple Silicon / Intel) | Linux (Ubuntu / RHEL) |

---

## 9. Troubleshooting Common Deployment Issues

### 1. Cassandra Cold-Start Latency
- **Symptom:** Backend reports `NoHostAvailable` during the first 60 seconds of initial boot.
- **Resolution:** Cassandra initializes its cluster metadata and schema slowly on cold starts. The `docker-compose.yml` healthcheck is configured with `start_period: 90s` and `retries: 20` to ensure downstream dependencies wait until CQL port 9042 is fully ready.

### 2. Port Collisions on Host
- **Symptom:** `Bind for 0.0.0.0:8001 failed: port is already allocated`
- **Resolution:** Run `netstat -ano | findstr 8001` (Windows) or `lsof -i :8001` (Linux) to find the conflicting process, or change the published host port in `docker-compose.yml`.

### 3. Missing Gemini API Key
- **Symptom:** UI Assistant shows `AI Assistant is temporarily unavailable` and `/api/llm/status` reports `available: false`.
- **Resolution:** Ensure `.env` contains a valid `GEMINI_API_KEY`. Recreate the backend container using `docker compose up -d backend`.

