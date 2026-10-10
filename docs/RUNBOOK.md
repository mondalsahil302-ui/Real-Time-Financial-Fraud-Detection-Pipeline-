# System Operational Runbook

**Project:** Real-Time Financial Fraud Detection Platform  
**Target Submission:** Academic Defense & Technical Demonstration  
**Author:** Software Project Architect & Lead Operations Engineer  
**Date:** October 10, 2026  

---

## 1. Prerequisites & System Requirements

Before starting the application, ensure the host machine meets the following prerequisites:

| Requirement | Supported Version | Purpose |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 (PowerShell 5.1+ / CMD) | Host OS environment |
| **Python** | Python 3.11.x (64-bit) | Backend, Spark workers, ML inference, RAG |
| **Node.js & npm** | Node.js 18+ (LTS) / npm 9+ | Vite dev server & frontend dependencies |
| **Docker Desktop** | Docker Engine 24+ / Compose v2 | Kafka, Cassandra, Prometheus, Grafana |
| **Google Gemini Key** | Active API Key (`gemini-3.5-flash-lite`) | AI investigation & assistant reasoning |

---

## 2. Environment Setup

### 2.1 Python Virtual Environment
Open PowerShell in the repository root (`d:\Real-Time-Financial-Fraud-Detection-Pipeline-`):

```powershell
# Create virtual environment (if not already created)
py -3.11 -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install pinned dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2.2 Environment Variables Configuration
Copy the safe configuration template to `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Ensure `.env` contains your Gemini API key and verified model:
```ini
GEMINI_API_KEY=AIzaSy...your-gemini-key...
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=60
```
> [!IMPORTANT]
> Never commit `.env` to version control. The repository `.gitignore` strictly excludes `.env`.

---

## 3. Infrastructure Startup (Docker Compose)

Ensure Docker Desktop is running on the host, then start the containerized infrastructure:

```powershell
# Start Kafka, Cassandra, Prometheus, Grafana, Alertmanager
docker compose up -d

# Verify running containers
docker compose ps
```

*Note: Apache Cassandra requires approximately 60–90 seconds to initialize its keyspace on first boot.*

To verify infrastructure connectivity:
```powershell
.\.venv\Scripts\python.exe tools\health_check.py
```

---

## 4. Starting Application Services

Services can be started either via the **One-Click Launcher** or as **Individual Microservices**.

### Option A: Managed One-Click Launcher (Recommended for Demos)
Run the automated Windows batch launcher from CMD or PowerShell:

```cmd
scripts\start_project.cmd
```
This launcher checks prerequisites, confirms container health, starts the FastAPI Control Center (`:8001`), launches the Vite frontend (`:5173`), and monitors processes in separate console windows.

To inspect running services:
```cmd
scripts\status_project.cmd
```

---

### Option B: Individual Microservice Execution (Terminal by Terminal)

For development, testing, or debugging, run each component in its own activated virtual environment terminal:

#### 1. Backend Control Center API
```powershell
# Terminal 1: FastAPI Service (Port 8001)
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --reload
```
- Interactive Swagger Docs: `http://localhost:8001/docs`
- Health check: `http://localhost:8001/api/health`

#### 2. Frontend Control Center UI
```powershell
# Terminal 2: React / Vite Dashboard (Port 5173)
cd frontend
npm run dev
```
- Dashboard UI: `http://localhost:5173`

#### 3. Spark Structured Streaming Engine
```powershell
# Terminal 3: Stream Processing & Model Inference
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe streaming\spark_streaming.py
```
- Metrics endpoint: `http://localhost:8002/metrics`

#### 4. RAG Investigation Consumer
```powershell
# Terminal 4: Automated Alert Investigation & Gemini Explanations
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m rag.investigation.kafka_investigation_consumer
```
- Metrics endpoint: `http://localhost:8000/metrics`

#### 5. Transaction Ingestion (Producer)
```powershell
# Terminal 5: Synthetic Transaction Stream
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m producer.producer --max-transactions 50 --delay 0.1
```
*Alternatively, you can trigger batches directly from the UI using the built-in Batch Simulator.*

---

## 5. Verification & Testing

### 5.1 Verification of Gemini Configuration
Run the offline LLM verification tool to confirm Google API credentials and response schemas:

```powershell
# Step 1: Check raw Gemini connectivity
.\.venv\Scripts\python.exe tools\test_llm_connection.py

# Step 2: Test RAG context synthesis + structured response generation
.\.venv\Scripts\python.exe tools\test_llm_investigation.py

# Step 3: Check Control Center API gateway status
Invoke-RestMethod http://localhost:8001/api/llm/status
```

### 5.2 Automated Backend Test Suite
Run the comprehensive test suite (handles offline containers gracefully):

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
*Expected: 76 passed, 7 skipped (when Docker is offline), 0 failed.*

### 5.3 Frontend Unit Tests & Build Verification
From the `frontend/` directory:

```powershell
cd frontend

# Run unit tests
npm test

# Verify production build compilation
npm run build
```
*Expected: 2/2 test suites passing, zero build errors.*

---

## 6. Observability & Monitoring Dashboards

When monitoring containers are started (`scripts\start_monitoring.cmd` or `docker compose up -d`):

| Service | Local URL | Default Credentials | Description |
| :--- | :--- | :--- | :--- |
| **Grafana OSS** | `http://localhost:3000` | `admin` / `admin` | Fraud metrics, throughput, latency |
| **Prometheus** | `http://localhost:9090` | None | Scrape targets, time-series metrics |
| **Alertmanager**| `http://localhost:9093` | None | Alert firing rules, pipeline alerts |
| **API Docs** | `http://localhost:8001/docs`| None | FastAPI OpenAPI specification |
| **Control Center**| `http://localhost:5173` | None | Enterprise fraud analyst workspace |

---

## 7. Graceful Teardown & Clean Shutdown

To shut down all services without losing persisted database records:

### 1. Stop Application Processes
If launched via `scripts\start_project.cmd`:
```cmd
scripts\stop_project.cmd
```
If launched manually in separate terminals, press `Ctrl + C` in each window.

### 2. Stop Docker Infrastructure
```powershell
# Stop containers while preserving Cassandra and Kafka volumes
docker compose down

# Stop using the project script
powershell -ExecutionPolicy Bypass -File .\scripts\stop_all.ps1
```
> [!NOTE]
> Do NOT use `docker compose down -v` unless you explicitly want to wipe all transaction history, alerts, and Cassandra data volumes.

---

## 8. Troubleshooting Common Issues

### Issue 1: Port Collision on 8001 or 5173
- **Symptom:** `OSError: [WinError 10048] Only one usage of each socket address is normally permitted`
- **Solution:** Identify the process occupying the port and terminate it:
  ```powershell
  Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object OwningProcess
  Stop-Process -Id <PID> -Force
  ```

### Issue 2: Docker Engine Connection Refused
- **Symptom:** `npipe:////./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`
- **Solution:** Ensure Docker Desktop is started and the whale icon is solid green in the Windows system tray. The backend test suite is resilient and will automatically skip live container tests if Docker is stopped.

### Issue 3: Gemini API Authentication Error
- **Symptom:** `403 Forbidden` or `API key not valid`
- **Solution:**
  1. Verify `.env` contains `GEMINI_API_KEY=AIzaSy...` without quotes.
  2. Verify your API key has quota enabled for `gemini-3.5-flash-lite`.
  3. Run `.\.venv\Scripts\python.exe tools\test_llm_connection.py` to confirm.

### Issue 4: Cassandra Connection Refused on 9042
- **Symptom:** `cassandra.cluster.NoHostAvailable`
- **Solution:** Cassandra takes 60–90 seconds to initialize during cold starts. Check logs with:
  ```powershell
  docker compose logs -f cassandra
  ```
  Wait until `Startup complete` is displayed before launching Spark or consumers.

### Issue 5: Spark Streaming Checkpoint Lock
- **Symptom:** `AnalysisException: Concurrent update to the dataset was detected`
- **Solution:** Run `scripts\run_demo_50.cmd`, which generates isolated unique checkpoints under `%TEMP%`, or clear local dev checkpoints:
  ```powershell
  Remove-Item -Path "checkpoints/*" -Recurse -Force -ErrorAction SilentlyContinue
  ```

