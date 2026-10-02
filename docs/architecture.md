# System Architecture

## Overview

The repository implements a local real-time fraud-detection pipeline. Docker Compose provides Kafka and Cassandra; Python produces transaction events; Spark Structured Streaming enriches and scores them; Kafka topics carry low-risk transactions and fraud alerts.

## Data Flow

1. `producer/producer.py` reads PaySim rows and publishes JSON events to the `transactions` topic.
2. `streaming/spark_streaming.py` parses and validates events, builds 19 base + 14 behavioral features (33 total), and scores them with the Isolation Forest model.
3. Transactions scored L3/L4/L5 are routed directly to `fraud-alerts`.
4. Transactions scored L1/L2 are passed to the XGBoost second-stage classifier.
5. XGBoost fraud predictions (probability ≥ 0.90) are routed to `fraud-alerts`.
6. XGBoost low-risk predictions are routed to `low-risk-transactions`.
7. Cassandra is provided as an operational storage service for future application integrations.

## Key Components

| Component | Location | Responsibility |
| --- | --- | --- |
| Local services | `docker-compose.yml` | Kafka and Cassandra containers |
| Event producer | `producer/producer.py` | Publish PaySim transactions |
| Streaming pipeline | `streaming/spark_streaming.py` | Feature engineering, IF + XGBoost cascade scoring, and risk routing |
| Model training | `training/train_isolation_forest_final.py`, `training/train_xgboost_second_stage.py` | Train and export model artifacts |
| Model artifacts | `models/` | Models, feature manifests, and runtime configuration |
| Dataset | `data/` | PaySim input data |
| Tests | `tests/` | Kafka and Cassandra connectivity tests |
| Tools | `tools/` | Offline diagnostic and benchmarking utilities |
