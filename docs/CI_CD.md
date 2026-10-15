# Continuous Integration & Continuous Delivery (CI/CD) Guide

**Project:** Real-Time Financial Fraud Detection Platform  
**Target Architecture:** Multi-tier Event-Driven Streaming & Anomaly Detection Pipeline  
**CI/CD Engine:** GitHub Actions (`.github/workflows/ci.yml`)  
**Status:** IMPLEMENTED & VALIDATED  

---

## 1. Overview & Architecture

The CI/CD pipeline automates verification, security auditing, production compilation, and packaging across all tiers of the fraud detection platform:

```text
               Git Push / Pull Request (main, master, Sahil-mondal)
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
     [Backend Job]             [Frontend Job]         [Infra & Security]
     - Python 3.11             - Node.js 20           - Docker Compose Check
     - Dependency Install      - Clean `npm ci`       - Git `.env` Verification
     - Bytecode Validation     - Vitest Suite         - Hardcoded Secret Scan
     - pip-audit Scan          - Production Build     - Entrypoint File Checks
     - Pytest (83+ tests)      - npm audit (0 CVEs)
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │ (All Gates Pass)
                                      ▼
                             [Release Packaging]
                             - Package Production Tarball
                             - Store Deployable Artifacts
                             - Conditional CD Staging Trigger
```

---

## 2. Workflow Triggers & Execution Conditions

The workflow is located in `.github/workflows/ci.yml` and triggers on:
1. **Push events** to core branches: `main`, `master`, and `Sahil-mondal`.
2. **Pull requests** targeting: `main`, `master`, and `Sahil-mondal`.
3. **Manual execution (`workflow_dispatch`)** via the GitHub Actions UI.

Concurrency control is enabled (`cancel-in-progress: true`), preventing redundant runs when subsequent commits are pushed quickly.

---

## 3. Detailed Job Breakdown

### 3.1 Backend Job (`backend`)
- **Environment:** `ubuntu-latest`, Python 3.11.
- **Dependency Ingestion:** Installs core pipeline dependencies from `requirements.txt` and web service dependencies from `backend/requirements.txt` with Pip caching.
- **Bytecode & Syntax Verification:** Executes `python -m compileall -q -x "\.venv" .` ensuring all source modules compile without syntax errors.
- **Dependency Audit:** Runs `pip-audit` to detect known CVEs in Python libraries.
- **Test Execution:** Runs the full backend test suite:
  ```bash
  python -m pytest tests -q
  ```
  *Note: External LLM requests are mocked in unit tests, allowing full test coverage without requiring live external Gemini API quotas in CI.*

### 3.2 Frontend Job (`frontend`)
- **Environment:** `ubuntu-latest`, Node.js 20.
- **Clean Installation:** Runs `npm ci` against the version-controlled `frontend/package-lock.json`.
- **Unit Testing:** Executes frontend Vitest component tests (`AssistantPanel.test.tsx`, `ManualTransactionForm.test.tsx`).
- **Production Compilation:** Runs `npm run build` (`tsc -b && vite build`) to generate the optimized assets in `frontend/dist/`.
- **Node Security Audit:** Executes `npm audit --audit-level=high` (verified 0 vulnerabilities).
- **Artifact Preservation:** Uploads `frontend/dist/` as a GitHub Actions workflow artifact with a 14-day retention period.

### 3.3 Infrastructure & Security Job (`infrastructure-and-security`)
- **Docker Compose Syntax Validation:** Executes `docker compose config --quiet` to confirm Compose services (Kafka, Cassandra, Prometheus, Grafana, Alertmanager, cAdvisor) are error-free.
- **Secret Exposure Defense:** Verifies that `.env` is uncommitted and excluded via `.gitignore`.
- **Codebase Secret Scanning:** Scans tracked files for accidental leaks of Google API keys (`AIzaSy...`) or private tokens.
- **Entrypoint Verification:** Validates that core pipeline entry files (`backend/app/main.py`, `streaming/spark_streaming.py`, `producer/producer.py`, `models/isolation_forest_final.pkl`, etc.) exist and are properly referenced.

### 3.4 CD & Release Packaging Job (`release`)
- **Trigger:** Executes automatically when `backend`, `frontend`, and `infrastructure-and-security` jobs pass on `main`, `Sahil-mondal`, or semantic version tags (`v*`).
- **Packaging:** Packages application source code, configuration templates, and compiled frontend assets into an immutable, versioned release archive: `fraud-detection-platform-${{ github.sha }}.tar.gz`.
- **Artifact Upload:** Retains the deployable release archive for 30 days.

---

## 4. Required Secrets & Configuration

| Secret Name | Required For | Description | Default / Fallback |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Live E2E runs / Deployment | Google Gemini API key for production RAG investigations | Mapped to mock key in CI |
| `DOCKERHUB_USERNAME` | Container Publication (Optional) | Docker Hub registry username | If absent, image push is skipped |
| `DOCKERHUB_TOKEN` | Container Publication (Optional) | Docker Hub personal access token | If absent, image push is skipped |
| `DEPLOY_TARGET_SSH_HOST` | CD Staging / Production (Optional) | Remote target server host/IP | If absent, deployment is safely bypassed |
| `DEPLOY_TARGET_SSH_KEY` | CD Staging / Production (Optional) | SSH private key for remote deployment | If absent, deployment is safely bypassed |

> [!NOTE]
> CI unit and integration tests do **not** require production secrets. All tests execute reliably with zero secrets configured in GitHub repository settings.

---

## 5. Inspecting Failed GitHub Actions Runs

1. Navigate to your GitHub repository and select the **Actions** tab.
2. Select the relevant workflow run (e.g., `CI/CD Pipeline & Security Validation`).
3. Click on the failing job (`Backend Tests & Security Audit`, `Frontend Tests & Production Build`, or `Infrastructure & Secret Hygiene`).
4. Expand the failing step:
   - **Backend failure:** Inspect the Pytest failure report or `pip-audit` advisory output.
   - **Frontend failure:** Inspect TypeScript compile errors (`tsc -b`) or Vitest assertions.
   - **Infrastructure failure:** Inspect Docker Compose validation or missing entrypoint errors.
5. Fix the issue locally, run `.\.venv\Scripts\python.exe -m pytest tests -q` and `npm test`, then push the fix.

---

## 6. How to Create a Release

To trigger a formal release build:

1. Ensure all local tests and builds pass:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests -q
   cd frontend; npm run build
   ```
2. Create and push a signed Git tag:
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0: Academic Submission & Production Defense"
   git push origin v1.0.0
   ```
3. GitHub Actions will execute all CI validation gates and package the deployable release archive under the workflow artifacts.

---

## 7. Configuring Automated CD Deployment

When a production staging server or cloud environment (e.g., AWS EC2, GCP Compute Engine, Kubernetes cluster) becomes available:

1. Add the following repository secrets under **Settings → Secrets and variables → Actions**:
   - `DEPLOY_TARGET_SSH_HOST`
   - `DEPLOY_TARGET_SSH_USER`
   - `DEPLOY_TARGET_SSH_KEY`
2. Update the `Deployment Gate & Status Check` step in `.github/workflows/ci.yml` to trigger the remote deployment script:
   ```yaml
   - name: Deploy to Remote Server
     if: env.DEPLOY_TARGET_SSH_HOST != ''
     run: |
       ssh -i $SSH_KEY $DEPLOY_TARGET_SSH_USER@$DEPLOY_TARGET_SSH_HOST "
         cd /opt/fraud-pipeline &&
         git pull origin main &&
         docker compose up -d &&
         systemctl restart fraud-backend fraud-frontend
       "
   ```

---

## 8. What the CI Workflow Does Not Verify Automatically

To maintain fast feedback loops and respect resource limits, the workflow deliberately does not run:
1. **Live Multi-Minute Kafka/Spark Event Streams:** Multi-gigabyte PaySim streaming across Spark micro-batches is verified via component unit tests and localized offline mocks.
2. **Real Cloud Billing / Gemini API Quota Usage:** Live Gemini inference against live external Google API servers is validated manually via `tools/test_llm_connection.py` and `tools/test_llm_investigation.py` to prevent credential exposure and quota exhaustion in CI runners.
3. **Hardware GPU Acceleration:** Models run in CPU-compatible inference mode during CI.

