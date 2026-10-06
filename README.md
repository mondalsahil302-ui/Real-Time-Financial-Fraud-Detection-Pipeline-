# Real-Time Financial Fraud Detection Pipeline
## End-to-End Microservice Architecture

## Windows local run and observability

The baseline detector remains PaySim producer → Kafka `transactions` → Spark Structured Streaming → Isolation Forest/risk routing → XGBoost for L1/L2 → `fraud-alerts` or `low-risk-transactions`. Fraud alerts feed the investigation consumer, which combines Cassandra live history with the separate Chroma `fraud_knowledge` and `paysim_cases` collections, asks Gemini (gemini-3.5-flash-lite) for a structured explanation, and persists it in `fraud_detection.investigation_results`. Cassandra is the source of live account history; Chroma collections are domain knowledge and synthetic references.

### Setup

From PowerShell at the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env } else { Write-Host 'Keeping existing .env; review .env.example for any new optional settings.' }
```

Keep local settings and credentials in `.env`; do not commit that file. The checked-in Compose defaults support a local development-only Grafana login. Change it in `.env` before exposing Grafana beyond localhost. Ensure the existing Chroma database is built before investigations; do not rebuild it for routine runs.

### Infrastructure startup

Start Docker Desktop, then run the managed local launcher from the project root:

```cmd
scripts\start_project.cmd
```

It starts Docker Compose and the local Control Center API, Spark worker, investigation consumer, and frontend without waiting indefinitely. `scripts\status_project.cmd`, `scripts\validate_project.cmd`, and `scripts\stop_project.cmd` check service state, perform live checks, and stop only application processes launched by this script; stopping does not stop containers or remove persistent data. `scripts\start_all.ps1` remains available for starting infrastructure only.

The Control Center Batch Simulator defaults to 50 transactions (the recommended demo size) with a 0.10-second producer delay. For an isolated end-to-end demo, run:

```cmd
scripts\run_demo_50.cmd
```

The demo command requires Spark to be stopped so it can start one worker with a unique checkpoint under `%TEMP%` and `SPARK_STARTING_OFFSETS=latest`; it never removes or modifies the production checkpoint. If `:8002` is already occupied, run `scripts\stop_project.cmd` first, then run the demo command. The runner requires healthy dependencies, submits exactly 50 through the existing Control Center producer, waits a bounded period for processing/investigations, allows 15 seconds for metric scraping, and reports the actual observed counts. It does not force a fraud alert; transaction-aware AI checks use an alert from the demo batch or an existing real alert. Gemini is the only LLM: set `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.5-flash-lite` in `.env`, then verify with `python .	ools	est_llm_connection.py`; there is no fallback provider. Required Kafka topics are `transactions`, `fraud-alerts`, and `low-risk-transactions`; topic creation follows the existing Kafka setup.

Producer metrics include measured per-transaction mapping latency and Kafka send latency; the Control Center also records batch generation duration. Spark records actual micro-batch processing duration. These histograms are measured at the operation boundaries, not filled with synthetic values.

### Component configuration and data

`.env.example` documents Kafka topic/broker, Cassandra host/port/keyspace, RAG top-K/context bounds, Chroma path/collection names, Gemini model/timeout/temperature, metrics port, and local observability URLs. Cassandra tables and primary keys are defined in `database/schema.cql`: transactions and alerts are partitioned by `name_orig`; investigation results by `alert_id`. This lets the retriever use bounded partition queries. The Chroma collections are `fraud_knowledge` and `paysim_cases`, with 384-dimensional `sentence-transformers/all-MiniLM-L6-v2` embeddings. PaySim stays the authoritative raw dataset; Chroma stores bounded synthetic examples and profile documents.

The investigation consumer uses its own `fraud-investigation-service` group, validates alerts, persists results before committing offsets, and returns an existing Cassandra investigation on duplicate alert IDs. Gemini requests have a finite 60-second maximum and bounded retries; a repeated model failure is saved as a failed investigation before the offset is committed so a provider outage cannot hold later alerts indefinitely. Persistence failures leave the offset uncommitted and retry after a short delay. Malformed JSON or alerts without an ID are sent to the configurable `FRAUD_INVESTIGATION_DLQ_TOPIC` (`fraud-investigation-dead-letter`) before their source offset is committed; a failed DLQ write leaves the source offset uncommitted. Other transient dependency failures are not sent to the DLQ. Do not run multiple copies with the same group while debugging retries.

On Windows, Spark runs with two local worker threads, two shuffle partitions, and a maximum of 500 Kafka offsets per micro-batch by default. These limits bound local work without changing the models, thresholds, topics, or routing logic. The Isolation Forest artifact is loaded once per reusable Python worker from the existing model file rather than serialized into a Spark broadcast; its feature contract and prediction call remain unchanged.

### LOCAL MONITORING SETUP (Windows CMD)

The repository runs monitoring in Docker Compose, avoiding a second host installation on the same ports. Prometheus is pinned to **3.15.0**, Grafana OSS to **13.2.3**, and Alertmanager is included. Compose provisions the Prometheus datasource and six dashboards from `monitoring/`; Prometheus scrapes itself, the application process endpoints, and cAdvisor at a 5-second interval. cAdvisor reports Docker runtime metrics when available; it does not provide Windows host CPU or memory metrics.

Run these commands from `cmd.exe` in the repository root, with Docker Desktop running:

```cmd
scripts\install_monitoring.cmd
scripts\start_monitoring.cmd
scripts\status_monitoring.cmd
scripts\validate_monitoring.cmd
scripts\stop_monitoring.cmd
```

`install_monitoring.cmd` checks architecture and Compose configuration, pulls the pinned images, and starts monitoring safely on repeat runs. `stop_monitoring.cmd` stops only Prometheus, Grafana, Alertmanager, and cAdvisor; Kafka, Cassandra, and their data volumes are untouched. Dashboard files show only metrics actually instrumented by the project; Kafka broker lag, Cassandra internals, risk-level distributions, XGBoost scores, and LLM token use are not exposed by these application counters, so no such values are invented. Current dashboards are **Fraud Detection Pipeline** (overview), **Fraud Detection**, **Kafka**, **Cassandra**, **RAG and LLM Investigation**, and **Infrastructure and Application Health**.

| Service | URL |
| --- | --- |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3000> |
| Alertmanager | <http://localhost:9093> |
| Investigation consumer metrics, health, readiness | <http://localhost:8000/metrics>, `/health`, `/readiness` |

Start the app endpoints in separate activated Python terminals when using the pipeline: `python -m rag.investigation.kafka_investigation_consumer` (8000), `python producer\producer.py` (8001), and `python streaming\spark_streaming.py` (8002). Prometheus will report the fraud application target DOWN until its metrics process is started. Verify the target in **Prometheus → Status → Targets** or query `up{job="fraud-pipeline-app"}`. Grafana's default local development credentials are `admin` / `admin` unless overridden in `.env`; change the password before exposing the service beyond the local machine.

To run the 10-transaction smoke test, first check the existing counter namespace fix with `python -m pytest tests/test_producer_metrics_namespace.py -q`, and ensure Kafka, Spark, and the application processes are running. Then run `python -m producer.producer --max-transactions 10 --delay 0.05`; watch the transaction and event panels update. The producer run alone cannot validate Spark, investigations, or Cassandra if those consumers are not running.

### Monitoring

Prometheus listens on `9090`, Grafana on `3000`, Alertmanager on `9093`, and cAdvisor on `8080`. The investigation consumer exposes `/metrics`, `/health`, and `/readiness` on `8000`; the transaction producer exposes them on `8001`, and Spark exposes them on `8002`. Prometheus scrapes the host using `host.docker.internal`; the Grafana Prometheus datasource and the Fraud Detection Pipeline dashboard are provisioned from `monitoring/grafana/`. Spark publishes processed transaction, fraud-alert, low-risk, batch-duration, and batch-error metrics; the producer, RAG/LLM, Cassandra persistence, and investigation consumer publish bounded component counters. Recording rules aggregate low-cardinality event rates and LLM/failure ratios. Alerts cover pipeline inactivity, Kafka consumer/producer errors, Cassandra retrieval/write errors, RAG retrieval failures, LLM failures/timeouts, investigation failure rate, processing latency, container telemetry, and Prometheus target availability. The ten-minute no-traffic and sustained failure/latency windows avoid startup alerts. Windows host CPU/memory monitoring is not provided by Linux cAdvisor; cAdvisor here reports Docker container metrics where the Docker Desktop runtime exposes them.

Run operational checks:

```powershell
python .\tools\health_check.py
python .\tools\test_observability.py
python .\tools\test_llm_investigation.py
python -m pytest tests -q
```

`health_check.py` returns nonzero if a dependency is unreachable. The offline LLM investigation uses `rag_output/investigations/rag_test_transfer_context.json`, validates the structured result, and does not consume Kafka or persist to Cassandra. `test_observability.py` checks live Prometheus targets/metrics/rules and Grafana/Alertmanager availability. `test_full_pipeline.py` is the live Kafka→Spark→output→investigation smoke test and requires all services and the foreground application processes to be running; it uses synthetic account identifiers.

### Shutdown and troubleshooting

Stop producer, investigation consumer, and Spark with Ctrl+C in their terminals, then stop infrastructure while preserving data volumes:

```powershell
.\scripts\stop_all.ps1
```

This does not delete Kafka, Cassandra, Prometheus, or Grafana volumes. If Kafka is reachable but has no output, check that Spark is running and that its checkpoint belongs to the current job. Cassandra startup can take several minutes. A Gemini failure is explicit: verify `GEMINI_API_KEY`, `GEMINI_MODEL`, and provider reachability. A malformed LLM response becomes a controlled failed investigation with `missing_key` or `invalid_field` diagnostics; the offline artifact command can save a debug response under `rag_output/investigations/`. Docker Compose errors should be checked with `docker compose logs <service>` after Docker Desktop is available.

> **Project docs:** [Architecture](docs/architecture.md) | [Contributing](CONTRIBUTING.md) | [Security](SECURITY.md)

## 1. Project Overview

This project implements a real-time financial fraud detection platform using a microservice-oriented architecture.

The core technologies are:

- Apache Kafka — event streaming backbone
- Apache Spark Structured Streaming — real-time stream processing
- Isolation Forest — primary anomaly-detection model
- Apache Cassandra — operational persistent storage
- RAG + Vector Database — contextual knowledge retrieval
- LLM — human-readable investigation explanation
- Grafana — monitoring and observability
- Docker / Docker Compose — local service orchestration

The central detection path is:

```text
Transaction Producer
        ↓
Apache Kafka
        ↓
Apache Spark Structured Streaming
        ↓
19-Feature Engineering
        ↓
Pre-trained Isolation Forest
        ↓
Anomaly Score
        ↓
5-Level Risk Classification
        ↓
Fraud Alert Routing
        ↓
Apache Cassandra
        ↓
RAG Context Retrieval
        ↓
LLM Explanation
        ↓
Grafana Monitoring
```

The architecture intentionally separates detection, routing, storage, contextual retrieval, explanation, and observability.

---

# 2. High-Level Architecture

```text
                         ┌─────────────────────────┐
                         │ Transaction Producer    │
                         │ Service                 │
                         │ Python                  │
                         └────────────┬────────────┘
                                      │ PRODUCES
                                      ▼
                         ┌─────────────────────────┐
                         │ Apache Kafka            │
                         │                         │
                         │ transactions            │
                         │ fraud-alerts            │
                         └────────────┬────────────┘
                                      │ CONSUMES
                                      ▼
                ┌────────────────────────────────────────────┐
                │ Apache Spark Structured Streaming          │
                │                                            │
                │ Parse → Validate → Features → ML Scoring   │
                └─────────────────────┬──────────────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Pre-trained             │
                         │ Isolation Forest        │
                         │                         │
                         │ Anomaly Score           │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ 5-Level Risk Engine     │
                         │                         │
                         │ L1 Very Low             │
                         │ L2 Low                  │
                         │ L3 Medium               │
                         │ L4 High                 │
                         │ L5 Critical             │
                         └────────────┬────────────┘
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                  Low-Risk Path              Alert Path
                         │                         │
                         ▼                         ▼
                    Cassandra              Kafka fraud-alerts
                                                   │
                                                   ▼
                                          Fraud Alert Service
                                                   │
                                                   ▼
                                               Cassandra
                                                   │
                                         ┌─────────┴─────────┐
                                         ▼                   ▼
                                 Account History       RAG Knowledge
                                         │                   │
                                         ▼                   ▼
                                      Context Builder / RAG
                                                   │
                                                   ▼
                                              LLM Service
                                                   │
                                                   ▼
                                         Investigation Explanation
                                                   │
                                                   ▼
                                               Cassandra
                                                   │
                                                   ▼
                                                Grafana
```

---

# 3. Architecture Philosophy

The system follows a simple principle:

> **Each component performs one clearly defined responsibility.**

```text
Kafka
→ Move and retain events

Spark
→ Process streaming data

Isolation Forest
→ Detect unusual transactions

Risk Engine
→ Convert one anomaly score into five operational risk levels

Cassandra
→ Persist transactions, alerts, and investigation results

RAG
→ Retrieve relevant contextual knowledge

LLM
→ Explain the alert using the available evidence

Grafana
→ Show system health and performance
```

The LLM is deliberately not used as the primary fraud classifier.

---

# 4. End-to-End Transaction Story

A single transaction makes the architecture easier to understand.

Suppose a customer makes a ₹75,000 transfer.

```text
Customer
   ↓
Transaction Producer
   ↓
Kafka: transactions
   ↓
Spark
   ↓
19 features
   ↓
Isolation Forest
   ↓
Anomaly score
   ↓
Risk level
   ↓
Alert routing
   ↓
Cassandra / fraud-alerts
   ↓
RAG
   ↓
LLM
   ↓
Investigation explanation
   ↓
Grafana
```

The same transaction therefore passes through several services, but each service performs a different job.

---

# 5. Transaction Producer Service

## Responsibility

The Transaction Producer Service creates or receives transaction events and publishes them to Kafka.

Example:

```json
{
  "transaction_id": "TX1001",
  "type": "TRANSFER",
  "amount": 75000,
  "oldbalanceOrg": 90000,
  "newbalanceOrig": 15000,
  "oldbalanceDest": 10000,
  "newbalanceDest": 85000
}
```

The producer sends the event to:

```text
Kafka topic: transactions
```

## Producer role

```text
Transaction Producer
        ↓
Kafka
```

The producer should not contain the complete fraud-detection workflow.

---

# 6. Apache Kafka

Apache Kafka acts as the event-streaming backbone.

## Responsibilities

Kafka provides:

- event ingestion
- durable event retention according to topic configuration
- topic-based organization
- partitions for parallelism
- offsets for consumer progress
- consumer-group based consumption
- asynchronous decoupling between services

## Topics

### transactions

Raw incoming transaction events.

```text
transactions
├── Partition 0
├── Partition 1
└── Partition 2
```

### fraud-alerts

Transactions routed for investigation because they meet the alert policy.

```text
fraud-alerts
├── Partition 0
├── Partition 1
└── Partition 2
```

The current development environment uses three partitions for each topic.

---

# 7. Producer–Consumer Model

The producer/consumer relationship changes from stage to stage.

```text
Transaction Producer
      ↓
Kafka: transactions
      ↓
Spark Consumer
      ↓
Spark processing
      ↓
Kafka: fraud-alerts
      ↓
Alert Service Consumer
      ↓
Cassandra
```

Therefore Spark is both:

```text
Consumer of transactions
```

and:

```text
Producer of fraud-alerts
```

This is a central event-driven architecture pattern.

---

# 8. Kafka Partitions

A topic is split into partitions for scalable parallel processing.

```text
transactions
     │
 ┌───┼───┐
 ▼   ▼   ▼
P0  P1  P2
```

Partitions also provide ordering within each partition. Global ordering across multiple partitions is not implied.

Important:

```text
More partitions
≠
Automatically more throughput
```

The consumer side and processing resources must have enough parallel capacity to benefit from additional partitions.

---

# 9. Kafka Offset

Every record in a partition has an offset.

```text
Partition 0

Offset 0 → TX001
Offset 1 → TX002
Offset 2 → TX003
Offset 3 → TX004
```

Offsets let a consumer keep track of progress and are important for recovery and lag measurement.

---

# 10. Kafka Consumer Lag

Conceptually:

```text
Latest available position
          -
Consumer position
          =
Consumer lag
```

Example:

```text
Latest offset  = 100,000
Spark position = 98,000

Lag = 2,000
```

A growing lag is a sign that the downstream processing capacity is below the incoming workload.

---

# 11. Spark Structured Streaming

Apache Spark Structured Streaming is the streaming-processing layer.

Its job is to consume Kafka events and execute the transaction-processing pipeline.

```text
Kafka
  ↓
Spark Structured Streaming
  ↓
Parse
  ↓
Validate
  ↓
Feature Engineering
  ↓
ML Scoring
```

---

# 12. Micro-Batch Processing

The implementation uses Spark's micro-batch execution model.

Conceptually:

```text
Kafka continuously receives events
          ↓
Spark trigger
          ↓
Micro-batch 1
          ↓
Process
          ↓
Micro-batch 2
          ↓
Process
          ↓
...
```

A micro-batch contains the records available to the query for that processing cycle. The number of records is not fixed by the trigger interval alone.

---

# 13. Spark Trigger

A trigger answers:

> **When should Spark execute the next streaming processing cycle?**

Example:

```python
.trigger(processingTime="500 milliseconds")
```

Simple interpretation:

```text
Every roughly 500 ms
        ↓
Spark starts the next processing cycle
        ↓
process available data
```

Important distinction:

```text
Trigger
→ when to process

Batch size
→ how much data is available/allowed to be processed

Processing time
→ how long a batch actually takes

Latency
→ how long the transaction takes end to end
```

A 500 ms trigger does not guarantee 500 ms end-to-end latency.

---

# 14. Spark Checkpointing

The streaming query should have a checkpoint location.

Checkpointing preserves required progress/state information used for recovery according to the streaming query's semantics.

Conceptually:

```text
Process batch
     ↓
Persist checkpoint information
     ↓
Continue processing
```

---

# 15. Spark Processing Flow

Each micro-batch follows:

```text
Kafka records
      ↓
Read value
      ↓
Parse JSON
      ↓
Validate schema
      ↓
Create 19 features
      ↓
Prepare model matrix
      ↓
Isolation Forest scoring
      ↓
Risk classification
      ↓
Route result
```

---

# 16. Feature Engineering Contract

The streaming pipeline must reproduce the same 19-feature contract used to train and evaluate the selected Isolation Forest.

## Features

```text
1. step
2. amount
3. oldbalanceOrg
4. newbalanceOrig
5. oldbalanceDest
6. newbalanceDest
7. orig_balance_change
8. dest_balance_change
9. orig_balance_error
10. dest_balance_error
11. orig_zero_after
12. dest_zero_before
13. dest_zero_after
14. log_amount
15. type_CASH_IN
16. type_CASH_OUT
17. type_DEBIT
18. type_PAYMENT
19. type_TRANSFER
```

## Formulas

```python
orig_balance_change = oldbalanceOrg - newbalanceOrig

dest_balance_change = newbalanceDest - oldbalanceDest

orig_balance_error = amount - orig_balance_change

dest_balance_error = amount - dest_balance_change

orig_zero_after = (newbalanceOrig == 0).astype(int)

dest_zero_before = (oldbalanceDest == 0).astype(int)

dest_zero_after = (newbalanceDest == 0).astype(int)

log_amount = np.log1p(amount)
```

The transaction type is converted to the five one-hot columns listed above.

The following are excluded from model input:

```text
isFraud
isFlaggedFraud
nameOrig
nameDest
```

`isFraud` remains ground truth for offline evaluation only.

---

# 17. Model Serialization

The streaming system should use the already-trained model rather than retraining during inference.

Conceptually:

```text
Offline training
      ↓
Isolation Forest
      ↓
Serialize
      ↓
models/
```

Expected model artifacts include:

```text
models/
├── isolation_forest_final.pkl
├── isolation_forest_features.json
└── isolation_forest_config.json
```

The feature list and configuration are part of the deployment contract.

---

# 18. Isolation Forest Scoring

For each transaction, the model returns a continuous anomaly score.

The project uses:

```python
anomaly_score = -model.decision_function(X)
```

The working interpretation is:

```text
Low score
→ more normal-like

High score
→ more anomalous
```

This is an anomaly score, not a probability of fraud.

---

# 19. Five-Level Risk Engine

The system turns the continuous anomaly score into five operational risk levels.

Five levels require four boundaries:

```text
          T1       T2       T3       T4
           │        │        │        │
───────────┼────────┼────────┼────────┼──────────
 Level 1   Level 2  Level 3  Level 4  Level 5
```

The actual threshold values should be derived from validation analysis and frozen before production-style evaluation.

---

# 20. Risk Levels

## Level 1 — Very Low Risk

```text
Allow + Store
```

No expensive RAG/LLM investigation is required.

## Level 2 — Low Risk

```text
Allow + Monitor + Store
```

These transactions can still contribute to account history and monitoring metrics.

## Level 3 — Medium Risk

```text
Investigation Alert
→ RAG
→ LLM explanation
```

## Level 4 — High Risk

```text
High-priority alert
→ RAG
→ LLM explanation
```

## Level 5 — Critical Risk

```text
Critical alert
→ RAG
→ LLM explanation
→ Policy-defined intervention
```

Any actual transaction hold, block, or enhanced-verification action should be controlled by explicit fraud/risk policy rather than by the anomaly score alone.

---

# 21. Why Lower Risk Is Not Deleted

Levels 1 and 2 may bypass the expensive investigation path, but they should generally still be persisted.

This allows the system to answer later questions such as:

```text
What has this account been doing recently?
```

The lower-risk transactions can provide historical context when a later event is investigated.

The principle is:

```text
Ignore for expensive investigation
≠
Discard from the system
```

---

# 22. Fraud Alert Service

The Fraud Alert Service consumes:

```text
Kafka: fraud-alerts
```

Its responsibilities can include:

- validate the alert event
- apply routing policy
- assign/update alert status
- persist the alert
- forward high-risk events to investigation processing

The service is a consumer of the alert topic.

---

# 23. Apache Cassandra

Cassandra is the operational persistent-storage layer.

The current project keyspace is:

```text
fraud_detection
```

Conceptually:

```text
fraud_detection
├── transactions
├── fraud_alerts
└── investigation_results
```

Cassandra should be modeled around the queries required by the application rather than as a relational database with arbitrary cross-table joins.

---

# 24. Transactions Table

The transaction record can contain fields such as:

```text
transaction_id
event_time
transaction_type
amount
name_orig
old_balance_orig
new_balance_orig
name_dest
old_balance_dest
new_balance_dest
risk_score
risk_level / prediction
processing_time_ms
```

The precise production schema and partition key should be finalized around the actual access patterns.

---

# 25. Fraud Alerts Table

Conceptual fields:

```text
alert_id
transaction_id
event_time
amount
risk_score
risk_level
alert_type
model_version
status
```

Downstream investigation fields can be stored here or in a dedicated investigation table depending on the final design.

---

# 26. Investigation Results

Potential fields:

```text
alert_id
explanation
supporting_context
investigation_status
generated_at
```

This creates an auditable record of what the explanation layer produced.

---

# 27. RAG Architecture

RAG stands for Retrieval-Augmented Generation.

In this system, RAG is an investigation/context layer after detection.

It should answer:

> **What relevant context and knowledge apply to this alert?**

RAG can combine two major sources:

```text
1. Structured live context from Cassandra
2. Semantic knowledge from a vector database
```

---

# 28. Structured Live Context from Cassandra

Cassandra can provide:

```text
Recent account transactions
Recent amounts
Transaction frequency
Transaction-type history
Recent alerts
Account activity context
```

For example:

```text
Current transaction = ₹75,000

Recent activity:
₹1,200
₹2,000
₹1,800
₹3,100
₹75,000  ← current
```

This is live structured context.

---

# 29. Vector Database / RAG Knowledge Base

The semantic knowledge base can contain:

```text
Fraud rules
Investigation guidelines
Known fraud patterns
Feature definitions
Historical confirmed cases
Alert-handling procedures
```

Possible prototype vector stores include:

```text
ChromaDB
FAISS
```

Documents are typically processed as:

```text
Documents
   ↓
Chunking
   ↓
Embeddings
   ↓
Vector Database
   ↓
Semantic Retrieval
```

---

# 30. RAG Retrieval Flow

For a Level 3–5 alert:

```text
Current alert
      ↓
Build retrieval query
      ↓
Search vector database
      ↓
Retrieve relevant rules/patterns/cases
      ↓
Combine with Cassandra account history
      ↓
Create investigation context
```

RAG is retrieving supporting evidence; it is not replacing the primary detector.

---

# 31. LLM Service

The LLM receives the investigation context prepared by the system.

Inputs can include:

```text
Current transaction
Isolation Forest anomaly score
Risk level
Recent account history
Retrieved fraud rules
Relevant investigation guidance
Similar historical cases
```

The LLM then produces a readable explanation.

---

# 32. LLM Responsibilities

The LLM can:

- explain why the alert was generated
- summarize account behavior
- summarize relevant retrieved rules
- organize evidence
- prepare an investigation note
- highlight what an investigator should review

The LLM should not be treated as the primary fraud classifier.

The responsibility split is:

```text
Isolation Forest
→ DETECT

Risk Engine
→ CLASSIFY

Cassandra
→ PROVIDE LIVE HISTORY

RAG
→ RETRIEVE

LLM
→ EXPLAIN
```

---

# 33. Example Investigation

Suppose:

```text
Transaction ID = TX1001
Amount = ₹75,000
Type = TRANSFER
Anomaly score = 0.084
Risk level = HIGH
```

Cassandra might return:

```text
Recent transactions:
₹1,200
₹2,000
₹1,800
₹3,100
```

RAG may retrieve:

```text
Guidance:
Unusually large transfers that differ materially from
recent account behavior require enhanced investigation.
```

The LLM can then produce an explanation such as:

```text
Risk Level: HIGH

The transaction was flagged because the ₹75,000 transfer is
substantially larger than the account's recent transaction
pattern. Relevant investigation guidance recommends review
of unusually large transfers and recent account activity.

Investigation focus:
Review recent account activity and verify the transfer context.
```

The explanation is generated from supplied evidence and retrieved context.

---

# 34. Kafka + RAG + LLM Relationship

The event flow can be:

```text
Spark
  ↓
Kafka: fraud-alerts
  ↓
Alert Service
  ↓
Cassandra
  ↓
Investigation Event
  ↓
RAG
  ↓
LLM
  ↓
Explanation
```

If desired, a separate topic can later be introduced:

```text
fraud-explanations
```

for asynchronous explanation-result events.

---

# 35. RAG/LLM Cost Control

Not every transaction needs an LLM call.

A possible policy is:

```text
Level 1
→ store only

Level 2
→ store + monitor

Level 3
→ alert + RAG + LLM

Level 4
→ priority alert + RAG + LLM

Level 5
→ critical alert + RAG + LLM
```

This means the model still scores every transaction, while the expensive investigation path is reserved for higher-risk events.

---

# 36. Grafana

Grafana is the monitoring and observability layer.

It does not perform fraud detection.

It displays data and metrics coming from the system.

Conceptually:

```text
Kafka metrics
Spark metrics
Cassandra data/metrics
RAG metrics
LLM metrics
      ↓
Grafana
```

---

# 37. Grafana Dashboard Metrics

## Transaction velocity

```text
Transactions/sec
Transactions/min
Transactions/batch
```

## Alert volume

```text
Total alerts
Alerts by risk level
Alert rate
```

## Kafka

```text
Consumer lag
Messages/sec
Partition activity
```

## Spark

```text
Micro-batch duration
Input rows/sec
Processed rows/sec
Processing time
```

## Machine Learning

```text
Anomaly score distribution
Risk-level distribution
ML scoring time
```

## Cassandra

```text
Read latency
Write latency
Write rate
Errors
```

## RAG / LLM

```text
Retrieval latency
LLM response latency
Explanations generated
Failed explanation requests
Pending investigations
```

---

# 38. Latency

Latency means:

> **How long it takes for the transaction to move through the required processing path and receive a result.**

Conceptually:

```text
Transaction generated
       ↓
Kafka
       ↓
Spark
       ↓
Feature Engineering
       ↓
Isolation Forest
       ↓
Risk Classification
       ↓
Cassandra / Alert
```

A simplified latency decomposition can be thought of as:

```text
waiting/ingestion time
+
stream processing time
+
model scoring time
+
output/database time
=
end-to-end latency
```

Actual latency should be measured rather than inferred from a trigger setting.

---

# 39. Throughput

Throughput means:

> **How many transactions the system can successfully process per unit of time.**

For this project:

```text
transactions/second
```

Example:

```text
10,000 transactions/sec
```

The earlier offline Isolation Forest benchmark measured approximately 15,997 transactions/sec for its scoring workload. That number should not be presented as the end-to-end Kafka → Spark → Cassandra throughput.

End-to-end throughput must be measured with the complete streaming system under load.

---

# 40. Latency vs Throughput

```text
Latency
→ How long does one transaction take?

Throughput
→ How many transactions can we process per second?
```

A system can have low latency but insufficient throughput, or high throughput but poor per-transaction latency. Both need to be evaluated independently.

---

# 41. Kafka Backlog and Lag

Suppose:

```text
Incoming rate = 10,000 tx/sec
Processing capacity = 6,000 tx/sec
```

Then approximately:

```text
10,000 arrive
6,000 processed
4,000 remain
```

The remaining work creates backlog in the streaming path, with Kafka retaining unconsumed records according to its retention policy.

Conceptually:

```text
Incoming rate > Processing rate
        ↓
Backlog grows
        ↓
Consumer lag grows
        ↓
Waiting time grows
        ↓
Latency grows
```

---

# 42. Performance Optimization

The Day 4–5 optimization phase should measure:

```text
Kafka partition count
Spark parallelism
CPU
Memory
Trigger interval
Kafka source admission
Feature-engineering time
Model scoring time
Cassandra write time
End-to-end latency
```

Do not change configurations blindly. Benchmark before and after each meaningful tuning change.

---

# 43. Kafka Partition Tuning

The current development topics use three partitions.

A controlled experiment can compare configurations such as:

```text
3 partitions
vs.
6 partitions
```

For each configuration measure:

```text
Throughput
Latency
Consumer lag
CPU
Memory
```

The chosen partition count should be based on observed workload behavior and available parallelism.

---

# 44. Spark Tuning

Potential tuning areas include:

```text
Executor CPU
Executor memory
Parallelism
Micro-batch configuration
Python serialization overhead
Feature-engineering efficiency
Model inference efficiency
```

The objective is to make processing capacity high enough to sustain the target workload.

---

# 45. Load Testing

Run simulated transaction traffic at increasing rates, for example:

```text
500 tx/sec
1,000 tx/sec
2,000 tx/sec
5,000 tx/sec
10,000 tx/sec
```

Record for every load level:

```text
Input rate
Processed rate
Average latency
P95 latency
P99 latency
Batch duration
Kafka lag
ML scoring time
Cassandra write time
Alert volume
```

This determines the practical capacity of the system.

---

# 46. Sub-Second Latency Target

The project target is:

```text
End-to-end processing latency < 1 second
```

This must be demonstrated through measurement.

A 500 ms trigger does not prove a sub-second system.

For example:

```text
Kafka waiting       = 80 ms
Spark processing    = 130 ms
Feature engineering = 25 ms
ML scoring          = 10 ms
Cassandra write     = 40 ms
```

The real total must include any scheduling/waiting behavior relevant to the measurement definition.

---

# 47. Failure Handling

The architecture is designed so that downstream failures are not automatically equivalent to detection failure.

## Spark temporarily unavailable

Kafka can retain unconsumed events according to retention settings while Spark is unavailable.

## LLM unavailable

The detection result and alert should still be stored. Explanation can be processed later.

## RAG unavailable

The fraud alert remains valid. Context enrichment can be retried separately.

## Cassandra unavailable or slow

The system should surface database failure/latency through monitoring and the streaming pipeline should follow the chosen retry/error-handling strategy.

---

# 48. Observability of Every Stage

The architecture should make the following visible:

```text
Kafka
→ incoming rate, partition activity, consumer lag

Spark
→ batch duration, processed rows, processing rate

Isolation Forest
→ scoring latency, score distribution

Risk Engine
→ risk-level distribution

Cassandra
→ read/write latency and failures

RAG
→ retrieval latency and failures

LLM
→ response latency and failures

System
→ end-to-end latency and throughput
```

---

# 49. Model Versioning

Every alert should record which model generated its score.

Example:

```text
model_version = isolation_forest_v1
```

After a retraining cycle:

```text
model_version = isolation_forest_v2
```

This allows an alert to be traced back to the exact model version used at detection time.

---

# 50. Data and Model Lineage

The system should maintain a traceable lineage:

```text
Raw transaction
      ↓
Kafka event
      ↓
Spark transformation
      ↓
19 model features
      ↓
Isolation Forest
      ↓
Anomaly score
      ↓
Risk level
      ↓
Alert
      ↓
Cassandra record
      ↓
RAG context
      ↓
LLM explanation
```

This is useful for debugging, reproducibility, audits, and research documentation.


# 53. Deployment Sequence

Recommended implementation order:

```text
1. Start Kafka
2. Create Kafka topics
3. Start Cassandra
4. Verify transaction producer
5. Verify Kafka topic contents
6. Start Spark Structured Streaming
7. Verify micro-batch ingestion
8. Add JSON parsing
9. Add 19-feature engineering
10. Load serialized Isolation Forest
11. Generate anomaly scores
12. Implement 5-level risk engine
13. Publish fraud alerts
14. Persist transactions and alerts
15. Build RAG knowledge base
16. Add Cassandra context retrieval
17. Add LLM explanation service
18. Build Grafana dashboards
19. Run load tests
20. Tune Kafka/Spark/database performance
21. Finalize architecture documentation
```

---

# 54. Final Producer–Consumer Story

The system can be explained as:

```text
Transaction Producer
        │
        │ PRODUCES
        ▼
Kafka: transactions
        │
        │ CONSUMES
        ▼
Spark Structured Streaming
        │
        │ PRODUCES
        ▼
Kafka: fraud-alerts
        │
        │ CONSUMES
        ▼
Alert Service
        │
        ▼
Cassandra
        │
        ├──────────────► Account History
        │
        └──────────────► Investigation data
                              │
                              ▼
                             RAG
                              │
                              ▼
                             LLM
                              │
                              ▼
                         Explanation
```

The key idea is:

> A service can be a consumer of one topic and a producer of another event.

---

# 55. Complete System Responsibility Table

| Component | Main responsibility |
|---|---|
| Transaction Producer | Generate/publish transaction events |
| Apache Kafka | Event transport, retention, partitions, offsets |
| Spark Structured Streaming | Consume and process transactions in streaming micro-batches |
| Feature Engineering | Create the exact 19 model features |
| Isolation Forest | Produce anomaly scores |
| Risk Engine | Convert one score into five operational risk levels |
| Alert Service | Route, validate, and persist alert events |
| Apache Cassandra | Store operational transaction, alert, and investigation data |
| RAG Service | Retrieve relevant contextual knowledge |
| Vector Database | Store/search embedded investigation knowledge |
| LLM Service | Generate investigation-oriented explanation |
| Grafana | Monitor system health and performance |

---

# 56. Five-Level Architecture and Investigation Cost

The five-level architecture does not require running the Isolation Forest five times.

The model still runs once:

```text
Transaction
   ↓
Isolation Forest
   ↓
ONE anomaly score
   ↓
FOUR boundaries
   ↓
FIVE risk levels
```

The extra levels mainly affect routing.

For example:

```text
Level 1–2
→ store/monitor

Level 3–5
→ investigation
→ RAG
→ LLM
```

Therefore the five-level design can actually reduce downstream RAG/LLM workload by restricting expensive contextual processing to higher-risk alerts.

---

# 57. False-Negative Focus

The model-selection and threshold work emphasizes reducing missed fraud.

A false negative is:

```text
Actual fraud
+
Predicted normal
=
False negative
```

A false positive is:

```text
Actual legitimate
+
Predicted suspicious
=
False positive
```

The system therefore evaluates:

```text
Recall
False negatives
Precision
False positives
F1
PR-AUC
Alert volume
```

Threshold selection should not be based only on maximum recall or maximum F1. The operational alert burden must also be considered.

---

# 58. Threshold and Alert-Volume Trade-off

The current validation analysis showed:

```text
Recall     FN     FP     Alerts
50.0%      12     81       93
66.7%       8    183      199
70.8%       7    365      382
83.3%       4   3938     3958
91.7%       2  13038    13060
95.8%       1  20540    20563
```

This demonstrates that pushing recall higher can cause a very large increase in false alerts.

Therefore, the production risk policy should be selected with explicit consideration of:

```text
Desired fraud recall
+
Acceptable alert volume
+
Investigator capacity
+
False-positive burden
```

---

# 59. Real-World Risk Decision Principle

The project should not simply implement:

```text
95% recall = automatically best
```

Instead:

```text
Lower threshold
      ↓
More fraud potentially captured
      ↓
Fewer missed fraud cases
      ↓
More legitimate transactions flagged
      ↓
More alerts and investigation workload
```

The five-level system gives the architecture a way to distinguish degrees of anomalous behavior rather than treating all suspicious scores identically.

---

# 60. Security and Production Considerations

Before production deployment, consider:

```text
Kafka authentication/encryption
Cassandra authentication/encryption
Secret management
LLM API authentication
RAG document access control
PII handling
Audit logging
Model versioning
RAG knowledge versioning
Prompt/version tracking
Data retention
Access control
```

These are production-hardening items beyond the basic local prototype.

---

# 61. Final Architecture

```text
                         TRANSACTION EVENT
                                │
                                ▼
                    Transaction Producer Service
                                │
                                │ produces
                                ▼
                     Apache Kafka: transactions
                                │
                                │ consumes
                                ▼
                  Spark Structured Streaming
                                │
                       Micro-batch trigger
                                │
                                ▼
                  JSON Parse + Validation
                                │
                                ▼
                    19-Feature Engineering
                                │
                                ▼
                     Pre-trained Isolation
                           Forest Model
                                │
                                ▼
                         Anomaly Score
                                │
                                ▼
                    Five-Level Risk Engine
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
           Level 1–2          Level 3–4          Level 5
         Store/Monitor        Alert + RAG       Critical + RAG
             │                  │                  │
             ▼                  └────────┬─────────┘
         Cassandra                      ▼
                                 Kafka: fraud-alerts
                                         │
                                         ▼
                                  Fraud Alert Service
                                         │
                                         ▼
                                      Cassandra
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                       Live Account Data       RAG Knowledge Base
                              │                     │
                              └──────────┬──────────┘
                                         ▼
                                    Context Builder
                                         │
                                         ▼
                                    LLM Service
                                         │
                                         ▼
                                Explanation / Report
                                         │
                                         ▼
                                      Cassandra
                                         │
                                         ▼
                                       Grafana
```

## Cassandra persistence (local development)

The pipeline writes two distinct output topics. Independent Cassandra consumers persist them into separate tables; investigation rows are reserved for a future RAG/LLM service.

```text
low-risk-transactions -> fraud_detection.transactions
fraud-alerts          -> fraud_detection.fraud_alerts
future investigation  -> fraud_detection.investigation_results
```

The `transaction_id` emitted by Spark is retained across transaction and alert rows. Spark currently does not emit `alert_id`; the alert consumer creates a stable UUID from `transaction_id` so a Kafka replay remains idempotent. `event_date` and `event_hour` are derived in UTC from Spark's ISO-8601 `event_time`. XGBoost fields are nullable on direct Isolation Forest alerts because that route does not run the second-stage classifier.

`anomaly_score` is an Isolation Forest anomaly score, not a fraud probability; risk levels describe routing suspicion, not ground truth. `xgboost_probability` is the second-stage probability, and `final_prediction` is the classifier decision. Cassandra stores the events for operational history and investigation context; it is not a classifier. Structured investigation lists/documents are stored as JSON text.

### Start Cassandra

```powershell
docker compose up -d cassandra
docker compose ps
docker logs fraud-cassandra --tail 50
```

The Compose service is named `cassandra`, its container is `fraud-cassandra`, and it exposes port `9042` on localhost.

### Install dependencies

`cassandra-driver` and `python-dotenv` are already listed in `requirements.txt`. To install them directly in the active environment:

```powershell
python -m pip install cassandra-driver python-dotenv
```

### Create schema and test connection

```powershell
python -m database.create_tables
python -m database.cassandra_connection
```

### Run Cassandra checks

With Cassandra running and the schema created:

```powershell
python -m unittest discover -s tests -p "test_cassandra_*.py" -v
python .\tools\test_cassandra_insert.py
```

The smoke test inserts synthetic transaction, alert, and investigation rows, reads them back, then deletes them.

### Run the persistence consumers

Run each consumer in a separate terminal. They use independent consumer groups and commit a message offset after its Cassandra insert succeeds.

```powershell
python .\database\transaction_consumer.py
```

```powershell
python .\database\fraud_alert_consumer.py
```
# Fraud Detection Control Center (Windows)

The React/Vite control center operates the existing PaySim → Kafka → Spark → model/risk routing pipeline. It calls the existing `producer.produce_batch` implementation, reads decision events from Kafka, and reads investigation results from the existing Cassandra table. Control Center batch history and AI chat conversations are stored in `backend/data/control_center.sqlite3`; this local control-plane database does not replace Kafka or Cassandra.

## Architecture and local ports

| Service | Address |
|---|---|
| Frontend | http://localhost:5173 |
| FastAPI and Swagger | http://localhost:8001 · http://localhost:8001/docs |
| Application metrics | http://localhost:8000/metrics |
| Producer metrics | http://localhost:8003/metrics |
| Spark metrics | http://localhost:8002/metrics |
| Kafka | localhost:9092 |
| Cassandra | localhost:9042 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Alertmanager | http://localhost:9093 |
| cAdvisor | http://localhost:8080 |
| Gemini | https://ai.google.dev (server-side API key) |

The control API queries Prometheus on the server side, returns its actual target health and scrape details, exposes metrics from the configured Prometheus queries, and discovers Grafana dashboard links from Grafana's API. Unavailable services and empty metric series are reported as unavailable; no synthetic status or metric values are used.

## Start and stop

1. Start the existing infrastructure only if needed: `docker compose up -d kafka cassandra prometheus grafana alertmanager cadvisor`. This reuses the configured containers and volumes.
2. Install API requirements once: `.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`.
3. Install frontend packages once: `cd frontend` then `npm install`.
4. Return to the repository root and run `scripts\start_control_center.cmd`.
5. Open http://localhost:5173. The app's API is http://localhost:8001 and Swagger is http://localhost:8001/docs.

Use `scripts\start_backend.cmd` and `scripts\start_frontend.cmd` to launch either part. `scripts\status_control_center.cmd` checks the UI/API, `scripts\validate_control_center.cmd` runs compile, Python tests, frontend tests/build, and live UI/API checks, and `scripts\stop_control_center.cmd` stops only listeners on ports 8001 and 5173. These scripts do not stop Kafka, Cassandra, Spark, Prometheus, Grafana, Alertmanager, or cAdvisor.

## Transactions, batches, and AI

The Batch Simulator validates a requested count and delay, records requested/generated/sent/failed values separately, sends through the existing producer, and streams batch updates over WebSocket. Spark decisions are observed from the existing fraud and low-risk Kafka topics; investigations are correlated from Cassandra and are not assumed to be complete just because an alert exists. The Transactions page also accepts one manual transaction using the existing PaySim field names and shows Kafka's actual partition/offset acknowledgement. Generated data is still classified only by the existing Spark pipeline.

The AI Assistant uses the existing Cassandra/Chroma retrievers and the server-side Gemini provider (LLM_PROVIDER=gemini, GEMINI_MODEL=gemini-3.5-flash-lite). It keeps conversations scoped to a transaction, validates cited evidence IDs against retrieved sources, and reports missing evidence. General questions are answered from the implemented pipeline architecture and the existing fraud knowledge collection. The API key never leaves the backend.

## Monitoring and troubleshooting

The Monitoring page refreshes at a five-second interval. It shows Prometheus targets, actual supported query results, Grafana dashboards returned by the Grafana API, and Alertmanager health. Open detailed dashboards directly in Grafana; the control center does not rely on iframe embedding. The Prometheus endpoint mapping is: application metrics `localhost:8000/metrics`, Control Center FastAPI `localhost:8001/metrics`, Spark metrics `localhost:8002/metrics`, producer metrics `localhost:8003/metrics`, and cAdvisor `cadvisor:8080/metrics` from inside the Prometheus container. The CLI producer exposes `/metrics` on port 8003 only while it is running; its target is expected to show down between batches, and no permanent-down alert is configured for it. After changing `monitoring/prometheus/prometheus.yml`, recreate or restart only the existing Prometheus service to load the config.

If the UI cannot reach the API, run `scripts\status_control_center.cmd` and check `http://localhost:8001/api/health`. If Kafka or Cassandra is unavailable, check `docker compose ps` and the relevant container logs. For an AI failure, check `http://localhost:8001/api/llm/status` and the server-side Gemini configuration. Prometheus/Grafana/Alertmanager outages leave the rest of the UI available and appear as unavailable in Monitoring. Set service URLs and ports in `.env`; defaults are documented in `.env.example`.
