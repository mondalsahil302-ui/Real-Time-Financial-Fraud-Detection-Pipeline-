# Real-Time Financial Fraud Detection Pipeline

### An end-to-end machine learning pipeline for detecting fraudulent financial transactions in real time.

---

## Overview

The **Real-Time Financial Fraud Detection Pipeline** analyzes financial transactions and identifies potentially fraudulent activity using machine learning and real-time data technologies.

The project uses the **PaySim transaction dataset** and combines machine learning models with **Apache Kafka** for transaction streaming and **Apache Cassandra** for transaction storage.

---

## Objectives

| Component | Purpose |
|---|---|
| 🔍 Fraud Detection | Identify potentially fraudulent transactions |
| 🤖 Machine Learning | Detect unusual transaction patterns |
| 📡 Real-Time Streaming | Stream transactions using Kafka |
| 🗄️ Data Storage | Store processed transactions in Cassandra |
| 📊 Model Evaluation | Measure fraud detection performance |

---

## Technology Stack

- **Python 3.11**
- **Pandas**
- **Scikit-learn**
- **Isolation Forest**
- **Autoencoder**
- **Apache Kafka**
- **Apache Cassandra**
- **Docker**
- **Git & GitHub**

---

## Project Workflow

```text
PaySim Dataset
      ↓
Feature Engineering
      ↓
Machine Learning Models
      ↓
Fraud / Anomaly Detection
      ↓
Kafka Transaction Streaming
      ↓
Cassandra Storage


Machine Learning:

Isolation Forest

Isolation Forest is used as an anomaly detection model to identify transactions that differ from normal transaction patterns.

Autoencoder:

An Autoencoder is trained primarily on normal transactions. Transactions with higher reconstruction error can be treated as potential anomalies.

Both approaches are evaluated using fraud labels available in the PaySim dataset.

Real-Time Pipeline

Apache Kafka

Kafka is used to stream financial transactions through the pipeline.

Transaction → Kafka Producer → fraud-transactions Topic

Apache Cassandra
Cassandra is used to store transaction information after it is processed.

Stored information includes:
Transaction type
Transaction amount
Origin and destination balances
Fraud status
Fraud flag
Transaction step

Real-Time-Financial-Fraud-Detection-Pipeline/
│
├── data/
│   └── PaySim dataset
│
├── src/
│   ├── paysim_data_loader.py
│   ├── train_isolation_forest.py
│   ├── evaluate_isolation_forest.py
│   ├── train_autoencoder.py
│   ├── evaluate_autoencoder.py
│   ├── kafka_transaction_producer.py
│   ├── cassandra_connection.py
│   └── test_cassandra_storage.py
│
├── README.md
└── ...
