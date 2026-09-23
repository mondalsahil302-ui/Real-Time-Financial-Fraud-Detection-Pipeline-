# 🚨 Real-Time Financial Fraud Detection Pipeline

> An end-to-end financial fraud detection project using **Machine Learning, Apache Kafka, and Apache Cassandra** to analyze and process financial transactions.

---

## 🎯 Project Objective

Financial fraud detection requires identifying unusual transaction patterns quickly and reliably.

This project uses the **PaySim financial transaction dataset** to:

- 📊 Analyze historical transaction data
- 🧹 Prepare and engineer features for fraud detection
- 🤖 Train anomaly detection models
- 📈 Evaluate model performance
- ⚡ Stream transactions using Apache Kafka
- 🗄️ Store processed transactions in Apache Cassandra

The project is being developed incrementally, with the current implementation covering **data preparation, machine learning, transaction streaming, and Cassandra storage**.

---

# 🏗️ Project Architecture

```text
                    ┌─────────────────────┐
                    │   PaySim Dataset    │
                    │   CSV Transactions  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Data Preparation   │
                    │  & Feature          │
                    │  Engineering        │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
       ┌──────────────────┐        ┌──────────────────┐
       │  Isolation       │        │   Autoencoder    │
       │  Forest          │        │   Model          │
       └────────┬─────────┘        └────────┬─────────┘
                │                           │
                ▼                           ▼
       ┌──────────────────┐        ┌──────────────────┐
       │ Model Evaluation │        │ Model Evaluation │
       └──────────────────┘        └──────────────────┘


                    Transaction Streaming
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Kafka Transaction   │
                 │ Producer            │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Apache Kafka        │
                 │ fraud-transactions  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Apache Cassandra    │
                 │ fraud_detection     │
                 │ transactions        │
                 └─────────────────────┘



📅 Project Progress
✅ Week 1 — Data Preparation
Completed
Loaded the PaySim dataset
Inspected dataset size and columns
Checked the number of fraudulent transactions
Prepared transaction data for machine learning
Created engineered transaction and balance-related features
Main file

paysim_data_loader.py

Loads the PaySim dataset and provides basic information about the data.

🤖 Week 2 — Machine Learning

Two anomaly detection approaches are currently implemented.

🌲 1. Isolation Forest

Isolation Forest is an unsupervised anomaly detection algorithm.

The idea is to identify transactions that behave differently from normal transaction patterns.

Training

File:

src/train_isolation_forest.py

Responsibilities:

Load PaySim data
Create transaction features
Create balance-related features
Encode transaction type
Train the Isolation Forest model
Save the trained model

Output:

src/isolation_forest_model.pkl
Evaluation

File:

src/evaluate_isolation_forest.py

Responsibilities:

Load the trained model
Generate anomaly scores
Test different detection thresholds
Calculate:
True Positives
False Positives
False Negatives
Precision
Recall
Generate a confusion matrix
Generate a classification report
🧠 2. Autoencoder

The second approach uses an Autoencoder neural network for anomaly detection.

The Autoencoder learns to reconstruct normal transaction patterns.

If a transaction produces a relatively high reconstruction error, it can be considered anomalous based on the selected threshold.

Training

File:

src/train_autoencoder.py

Responsibilities:

Load PaySim data
Select normal transactions
Create engineered features
Encode transaction type
Handle invalid values
Scale the features
Train the Autoencoder
Save the model, encoder, scaler, and threshold

Output:

src/autoencoder_model.pkl
Evaluation

File:

src/evaluate_autoencoder.py

Responsibilities:

Load the trained Autoencoder
Calculate reconstruction errors
Test multiple percentile thresholds
Calculate precision, recall, and F1-score
Select a threshold using validation data
Evaluate the selected threshold on unseen test data
⚡ Week 2 — Real-Time Transaction Streaming

After developing the machine learning components, the project also includes a transaction streaming layer.

Kafka

Apache Kafka is used as the event streaming platform.

Transactions from the PaySim dataset are published to a Kafka topic.

Kafka Producer

File:

src/kafka_transaction_producer.py

Responsibilities:

Read transactions from the PaySim dataset
Convert each transaction into a Python dictionary
Send transactions to Kafka
Store the same transaction in Cassandra
Display transaction processing information

Kafka configuration:

Kafka Server: localhost:9092
Topic: fraud-transactions

Example output:

Processed: PAYMENT | Amount: 6440.78 | Fraud: 0
Processed: CASH_OUT | Amount: 47458.86 | Fraud: 0
Processed: TRANSFER | Amount: 42712.39 | Fraud: 0
🗄️ Cassandra Storage

Apache Cassandra is used as the transaction storage database.

A Cassandra keyspace named:

fraud_detection

contains the:

transactions

table.

The streaming producer inserts processed transactions into Cassandra.

Cassandra Connection

File:

src/cassandra_connection.py

Purpose:

Connect Python to the Cassandra container
Connect to the fraud_detection keyspace
Verify that the Cassandra connection works

Example:

Connected to Cassandra successfully!
Cassandra Storage Test

File:

src/test_cassandra_storage.py

Purpose:

Test whether transactions can be inserted into Cassandra
Verify that the transactions table is working correctly

Example test transaction:

transaction_id: TEST001
type: PAYMENT
amount: 100
is_fraud: 0

This was used to verify the Cassandra storage layer before connecting it to the streaming producer.

🔄 Current Transaction Flow

The current streaming implementation follows this flow:

        PaySim CSV
            │
            ▼
   Kafka Transaction
       Producer
            │
            ├───────────────► Apache Kafka
            │                 │
            │                 └── fraud-transactions
            │
            ▼
       Cassandra
            │
            ▼
    fraud_detection
       transactions

The current producer sends the transaction to Kafka and stores the transaction in Cassandra.

📂 Project Structure
Real-Time-Financial-Fraud-Detection-Pipeline/
│
├── data/
│   └── PS_20174392719_1491204439457_log.csv
│
├── src/
│   │
│   ├── paysim_data_loader.py
│   │
│   ├── train_isolation_forest.py
│   ├── evaluate_isolation_forest.py
│   ├── isolation_forest_model.pkl
│   │
│   ├── train_autoencoder.py
│   ├── evaluate_autoencoder.py
│   ├── autoencoder_model.pkl
│   │
│   ├── kafka_transaction_producer.py
│   │
│   ├── cassandra_connection.py
│   └── test_cassandra_storage.py
│
└── README.md