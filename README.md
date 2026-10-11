# Real-Time Financial Fraud Detection Pipeline

A machine learning pipeline for detecting potentially fraudulent financial transactions using anomaly detection and real-time data technologies.

## Overview

This project uses the **PaySim dataset** to identify unusual transaction patterns.

It combines:

- Machine Learning for fraud/anomaly detection
- Apache Kafka for transaction streaming
- Apache Cassandra for transaction storage

## Machine Learning

### Isolation Forest
Detects transactions that differ from normal transaction patterns.

### Autoencoder
Trained mainly on normal transactions. Transactions with higher reconstruction error are treated as potential anomalies.

Both models are evaluated using the fraud labels provided by the PaySim dataset.

## Model Evaluation

Two anomaly-detection approaches were implemented during Week 1 and Week 2:

### 1. Isolation Forest

Isolation Forest was implemented as an unsupervised anomaly-detection baseline.

- Training samples: 5,090,096
- Testing samples: 1,272,524
- Features: 16
- Model: `IsolationForest`
- Saved model: `src/isolation_forest_model.pkl`

At the selected evaluation threshold of `-0.05`:

- True Positives: 0
- False Positives: 31
- False Negatives: 1,643
- Recall: 0%
- Precision: 0%

### 2. Autoencoder

The Autoencoder was trained mainly using normal transactions and detects potential fraud using reconstruction error.

Final test results:

| Metric | Result |
|---|---:|
| True Positives | 594 |
| False Positives | 642 |
| False Negatives | 1,049 |
| Recall | 36.23% |
| Precision | 48% |
| F1-score | 0.41 |

The validation process selected a reconstruction-error threshold of approximately `0.04557`.

### Current Model Selection

Based on the Week 1 and Week 2 experiments, the **Autoencoder is currently used as the primary anomaly-detection approach**, while Isolation Forest is retained as a baseline/comparison model.

## Real-Time Pipeline
```text
PaySim Dataset
      |
      v
Feature Engineering
      |
      v
Machine Learning
      |
      v
Fraud / Anomaly Detection
      |
      v
Kafka Streaming
      |
      v
Cassandra Storage

Kafka

Kafka is used to stream transactions through the fraud-transactions topic.

Transaction -> Kafka Producer -> fraud-transactions
Cassandra

Cassandra stores processed transaction information such as:

Transaction type
Transaction amount
Account balances
Fraud status
Fraud flag
Transaction step

Project Structure
Real-Time-Financial-Fraud-Detection-Pipeline/
|
├── data/
│   └── PaySim dataset
|
├── src/
│   ├── paysim_data_loader.py
│   ├── train_isolation_forest.py
│   ├── evaluate_isolation_forest.py
│   ├── train_autoencoder.py
│   ├── evaluate_autoencoder.py
│   ├── kafka_transaction_producer.py
│   ├── cassandra_connection.py
│   └── test_cassandra_storage.py
|
├── requirements.txt
├── README.md
└── .gitignore

Technologies
Python
Pandas
NumPy
Scikit-learn
Isolation Forest
Autoencoder
Apache Kafka
Apache Cassandra
Docker
Git & GitHub

