https://youtu.be/HWaJKcaynJg?si=ffgDCXvmw0CPTdt5
PROJECT SAMPLE VIDEO LINK
# Real-Time Financial Fraud Detection Platform

> **Enterprise Stream-Processing, Machine Learning Anomaly Detection, RAG Knowledge Retrieval & Generative AI Investigation System**

[![CI/CD Pipeline & Security Validation](https://github.com/mondalsahil302-ui/Real-Time-Financial-Fraud-Detection-Pipeline-/actions/workflows/ci.yml/badge.svg)](https://github.com/mondalsahil302-ui/Real-Time-Financial-Fraud-Detection-Pipeline-/actions)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-20_LTS-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/Docker_Compose-v2-blue.svg)](https://docs.docker.com/compose/)

---

## 1. Executive Overview & Purpose

The **Real-Time Financial Fraud Detection Platform** is a production-grade, distributed microservice architecture designed to detect, classify, route, and investigate suspicious financial transactions in real-time.

It integrates high-throughput event streaming (**Apache Kafka**), real-time stream feature enrichment (**Apache Spark Structured Streaming**), unsupervised anomaly detection (**Isolation Forest**), supervised second-stage classification (**XGBoost**), operational state persistence (**Apache Cassandra**), context-grounded retrieval-augmented generation (**Chroma Vector DB**), natural language explanation (**Google Gemini 3.5 Flash Lite**), and an interactive operations dashboard (**FastAPI + React 18 / Vite**).

```text
Transaction Source (PaySim CSV / Simulator)
       │
       ▼
     Kafka (Topic: `transactions`)
       │
       ▼
Spark Structured Streaming (19 Base + 14 Behavioral = 33 Features)
       │
       ▼
Fraud Detection Models (Primary: Isolation Forest | Secondary: XGBoost)
       │
       ▼
Risk Score / Prediction / Decision (L1-L5 Multi-Level Risk Engine)
       │
       ├── Low-Risk Path (L1/L2) ──────► Kafka: `low-risk-transactions`
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
                                       Gemini — Sole LLM (`gemini-3.5-flash-lite`)
                                                  │
                                                  ▼
                                       Investigation / Structured Explanation
                                                  │
                                                  ▼
                                       React Control Center (Vite Dashboard / Port 5173)
```

---

## 2. Key Architectural Features

- **33-Feature Streaming Pipeline:** Dynamically derives 19 base financial ratios plus 14 rolling per-account velocity and depletion attributes across micro-batches.
- **Two-Stage Machine Learning Cascade:** Unsupervised Isolation Forest flags statistical anomalies into 5 risk tiers (L1–L5); borderline transactions (L1/L2) pass to a second-stage XGBoost model for secondary confirmation.
- **Strict Role Separation:** Generative AI is confined exclusively to investigation explanation and analyst reasoning. Gemini never scores transactions or overrides ML classifications.
- **Context-Grounded RAG:** Assembles live account history from Cassandra with regulatory guidance and historical typologies from ChromaDB.
- **Enterprise Control Center:** Modern React 18 interface providing live batch simulations, transaction drill-downs, and conversational AI investigations.
- **Full-Stack Observability:** Scrapes Kafka, Spark, Cassandra, and API telemetry into Prometheus with 6 pre-provisioned Grafana dashboards.

---

## 3. Project Documentation Index

- **[System Architecture & Directory Structure](docs/PROJECT_STRUCTURE.md):** Detailed module breakdown and data contracts.
- **[Deployment & Containerization Guide](docs/DEPLOYMENT.md):** Production Docker setup, multi-stage builds, and resource allocations.
- **[Security Architecture & Audit Guide](docs/SECURITY.md):** Non-root containers, secret handling, prompt injection defenses, and CORS.
- **[Continuous Integration & Delivery (CI/CD)](docs/CI_CD.md):** GitHub Actions workflow, test automation, and release packaging.
- **[Operational Runbook](docs/RUNBOOK.md):** Step-by-step local commands, startup scripts, and port management.
- **[Security Validation Report](docs/SECURITY_VALIDATION.md):** CVSS/OWASP vulnerability evaluation results.

---

## 4. Prerequisites

Before running the application, ensure the host machine meets the following requirements:

| Component | Minimum Version | Notes |
| :--- | :--- | :--- |
| **Docker Engine / Desktop** | Version 24+ with Docker Compose v2 | Required for containerized execution |
| **Python** (Local Dev Only) | Python 3.11.x (64-bit) | Backend, Spark workers, and tests |
| **Node.js** (Local Dev Only)| Node.js 18+ LTS / npm 9+ | Control Center web development |
| **Gemini API Key** | Google Generative AI API Key | Configured in `.env` for AI investigations |
| **Hardware** | 4 CPU Cores, 8 GB RAM, 20 GB SSD | Recommended for complete Docker stack |

---

## 5. Environment Configuration

Before launching the platform, create a local environment configuration file from the safe `.env.example` template:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
docker compose build
docker compose up -d
docker compose ps
```

### Linux / macOS

```bash
cp .env.example .env
nano .env
docker compose build
docker compose up -d
docker compose ps
```

> [!IMPORTANT]
> - Replace all placeholders (such as `GEMINI_API_KEY=your_gemini_api_key_here` and `GRAFANA_ADMIN_PASSWORD=your_secure_grafana_password_here`) with your valid credentials before starting services.
> - The local `.env` file is excluded from Git tracking via `.gitignore` and from Docker image builds via `.dockerignore`.
> - **Never commit or publish your local `.env` file to version control.**

---

## 6. Docker Deployment (Recommended)

The entire microservice ecosystem can be built and launched with Docker Compose:

### Step 1: Build Application Images
```bash
docker compose build
```
*Builds `fraud-detection-api:1.0.0` (FastAPI backend) and `fraud-detection-frontend:1.0.0` (Nginx/React UI).*

### Step 2: Start All Services in Background
```bash
docker compose up -d
```

### Step 3: Inspect Service Health
```bash
docker compose ps
```

### Step 4: Access Endpoints
- **Control Center UI:** [http://localhost:5173](http://localhost:5173)
- **FastAPI Interactive Docs:** [http://localhost:8001/docs](http://localhost:8001/docs)
- **Grafana Observability:** [http://localhost:3000](http://localhost:3000) (`admin` / `admin`)
- **Prometheus Console:** [http://localhost:9090](http://localhost:9090)
- **Alertmanager:** [http://localhost:9093](http://localhost:9093)

### Step 5: Safe Teardown (Preserving Data)
```bash
docker compose down
```

---

## 7. Local Development Workflow (Without Docker)

If developing locally on Windows PowerShell:

```powershell
# 1. Activate Python virtual environment
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r backend\requirements.txt

# 2. Launch Docker infrastructure (Kafka, Cassandra, Monitoring)
docker compose up -d kafka cassandra prometheus grafana alertmanager cadvisor

# 3. Start Backend Control Center API
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload

# 4. Start Frontend (New Terminal)
cd frontend
npm run dev
```

Or execute the automated launcher script:
```cmd
scripts\start_project.cmd
```

---

## 8. Verifying & Running Tests

### Backend Test Suite (Pytest)
```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
*Expected: 83 passed, 0 failed.* (Integration tests gracefully skip when Cassandra or Kafka containers are offline).

### Frontend Component Tests (Vitest)
```powershell
cd frontend
npm test
```
*Expected: 2 passed, 2 total.*

### Frontend Production Build
```powershell
cd frontend
npm run build
```
*Expected: Clean compilation to `frontend/dist/` in <500ms.*

### Gemini Connectivity Verification
```powershell
.\.venv\Scripts\python.exe tools\test_llm_connection.py
```

---

## 9. Research Notebooks & Experiments

All experimental Jupyter Notebooks are preserved in the repository:
- `notebooks/Financial_Fraud_Anomaly_Detection_Complete.ipynb` (End-to-end 33-feature anomaly detection story)
- `notebooks/Patient_Anomaly_Detection_Complete.ipynb`
- `archive/notebooks/*.ipynb` (Historical Autoencoder vs Isolation Forest benchmarks)

To run notebooks independently of the production stack:
```powershell
.\.venv\Scripts\python.exe -m jupyter lab
```
*Note: Notebooks are excluded from production Docker images to maintain minimal container footprints.*

---

## 10. Data Persistence & Volume Management

The following Docker volumes survive container recreation:
- `cassandra_data`: Persists transaction records and Cassandra investigations.
- `kafka_data`: Persists Kafka partition logs.
- `backend_data`: Persists SQLite Control Center batch history.
- `vector_db_data`: Persists Chroma embeddings.
- `grafana_data` & `prometheus_data`: Persists dashboards and metric time-series.

To stop services without losing state, run `docker compose down`. Do **not** pass `-v` unless a complete state wipe is desired.

---

## 11. Security & Compliance Summary

- **Non-Root Containers:** Backend runs as unprivileged user `appuser` (UID 1000).
- **Strict CORS:** Restricted to local development origins; credentials disabled on open endpoints.
- **Sanitized Errors:** Catch-all exception handler in FastAPI prevents internal stack traces and filesystem disclosures.
- **Zero Committed Secrets:** Confirmed via static scanning; `.env` excluded from version control.
- Detailed audit: [docs/SECURITY.md](docs/SECURITY.md) and [docs/SECURITY_VALIDATION.md](docs/SECURITY_VALIDATION.md).

---

## 12. License & Attribution

This project is released under the Apache 2.0 License. PaySim synthetic transaction data is provided for research and benchmark demonstration purposes.
