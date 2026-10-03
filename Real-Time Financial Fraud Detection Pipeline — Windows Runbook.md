# Real-Time Financial Fraud Detection Pipeline — Windows Runbook

# Real-Time Financial Fraud Detection Pipeline

## Windows Runbook — Kafka \+ Spark Structured Streaming \+ Isolation Forest \+ XGBoost

### 1. Current pipeline

PaySim Producer → Kafka transactions → Spark Structured Streaming → 33-feature engineering → Isolation Forest → 5-level risk routing → XGBoost for L1/L2 → Kafka outputs fraud-alerts and low-risk-transactions.

Important evaluation note: the recent 1,000-row PaySim test slice contained 0 actual fraud and 1,000 legitimate transactions. Correctly predicted legitimate transactions are TN, not FN. This slice cannot measure fraud recall/F1/FNR.

### 2. Project root and environment

Project root:

D:\Real-Time-Financial-Fraud-Detection-Pipeline-

Activate:

```
cd D:\Real-Time-Financial-Fraud-Detection-Pipeline-
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python --version
pip --version
```
Optional syntax checks:

```
python -m py\_compile .\producer\producer.py
python -m py\_compile .\streaming\spark\_streaming.py
```
### 3. Start Kafka

```
cd D:\Real-Time-Financial-Fraud-Detection-Pipeline-
docker compose up -d kafka
docker compose ps
```
Check topics:

```
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```
Describe topics:

```
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic transactions
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic fraud-alerts
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic low-risk-transactions
```
### 4. Windows Hadoop native support

The stateful Spark job previously required Windows Hadoop native support.

Verify:

```
Test-Path C:\hadoop\bin\hadoop.dll
Test-Path C:\hadoop\bin\winutils.exe
$env:HADOOP\_HOME
```
Expected: both Test-Path commands return True and HADOOP\_HOME is C:\hadoop.

### 5. Start Spark

Use a dedicated terminal and keep it running:

```
cd D:\Real-Time-Financial-Fraud-Detection-Pipeline-
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m py\_compile .\streaming\spark\_streaming.py
python .\streaming\spark\_streaming.py
```
Expected banner values:

- Kafka input: transactions
- Low-risk topic: low-risk-transactions
- Fraud alert topic: fraud-alerts
- Isolation Forest feature count: 33
- XGBoost threshold: 0.90
- JSON state checkpoint: .\checkpoints\transactions\_risk\_33\_v5\_jsonstate

Normal warnings:

- AQE not supported for streaming/stateful workloads: informational.
- Processing time can exceed the 5-second trigger on a local Windows machine: performance warning, not necessarily a failure.

### 6. Start Kafka consumers

Fraud alerts:

```
docker exec -it fraud-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic fraud-alerts
```
Low-risk:

```
docker exec -it fraud-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic low-risk-transactions
```
The Kafka KIP-848 production-ready message is informational.

### 7. Run the basic producer

```
cd D:\Real-Time-Financial-Fraud-Detection-Pipeline-
.\.venv\Scripts\Activate.ps1
python .\producer\producer.py --max-transactions 1000 --delay 0.05
```
### 8. Run the PaySim test producer

For the dedicated test producer:

```
python .\tools\send\_paysim\_test.py 1000
```
The intended test construction is based on the first 500,000 chronological experiment rows, with the final 100,000 used as the held-out test region. The 1,000-row command is a smoke/routing test; it is not the final benchmark.

### 9. Clean run

Stop Spark with Ctrl\+C.

Remove only the current compatible state checkpoint:

```
Remove-Item -Recurse -Force .\checkpoints\transactions\_risk\_33\_v5\_jsonstate
```
For a completely clean Kafka experiment, delete/recreate the relevant topics only when previous messages are no longer needed:

```
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic transactions
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic fraud-alerts
docker exec fraud-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic low-risk-transactions
```
### 10. Recommended terminal layout

Terminal 1: Kafka

```
docker compose up -d kafka
```
Terminal 2: Spark

```
python .\streaming\spark\_streaming.py
```
Terminal 3: fraud-alerts consumer

```
docker exec -it fraud-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic fraud-alerts
```
Terminal 4: low-risk consumer / producer

```
docker exec -it fraud-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic low-risk-transactions
```
or

```
python .\tools\send\_paysim\_test.py 1000
```
### 11. Routing logic

L3/L4/L5 → fraud-alerts directly.

L1/L2 → XGBoost:

- probability >= 0.90 → fraud-alerts
- probability < 0.90 → low-risk-transactions

The output payload includes final\_prediction and final\_decision\_path.

### 12. Confusion matrix

- Actual fraud \+ predicted fraud = TP
- Actual fraud \+ predicted normal = FN
- Actual normal \+ predicted fraud = FP
- Actual normal \+ predicted normal = TN

For the recent 1,000-row test slice:

- actual fraud = 0
- actual normal = 1,000

Therefore a correctly predicted normal transaction is TN. The run cannot contain a genuine FN because there were no actual fraud examples.

### 13. Final 100,000-row evaluation requirement

For an apples-to-apples stateful streaming benchmark:

1. Start with a fresh compatible checkpoint.
2. Warm Spark state with the preceding 400,000 chronological transactions.
3. Then stream the final 100,000 held-out transactions.
4. Carry isFraud only as an evaluation/audit label, never as a model input.
5. Use a stable test\_row\_id or equivalent key to align ground truth with final prediction.
6. Report TP, TN, FP, FN, precision, recall, F1, PR-AUC, ROC-AUC, FPR and FNR.

Current limitation: the existing Kafka output payload does not include isFraud, so exact streaming TP/TN/FP/FN cannot yet be recovered directly from the two Kafka output topics.

### 14. Final checklist

\[ \] Correct project root

\[ \] .venv activated

\[ \] Kafka container is Up

\[ \] Required topics exist

\[ \] C:\hadoop native files verified

\[ \] Compatible Spark checkpoint used

\[ \] Spark process running

\[ \] fraud-alerts consumer open

\[ \] low-risk consumer open

\[ \] Producer sends intended test data

\[ \] Output records are observed

\[ \] Ground truth aligned to the test records

\[ \] Final benchmark uses the held-out test population
