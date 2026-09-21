# Real-Time Financial Fraud Detection Pipeline

A real-time financial fraud detection pipeline using the PaySim dataset, Kafka, Cassandra, and machine learning models for anomaly detection.

## Project Overview

This project focuses on building a real-time financial transaction monitoring system that can identify potentially fraudulent transactions.

The project uses historical PaySim transaction data to train anomaly detection models and simulates real-time transaction streaming using Kafka. Cassandra is used for storing transaction records.

The planned architecture will later integrate Spark Structured Streaming for real-time ML inference and monitoring tools for visualization and performance analysis.

---

## Current Architecture

```text
PaySim Dataset
      |
      v
Python Data Loader
      |
      v
Feature Engineering
      |
      +----------------------+
      |                      |
      v                      v
Isolation Forest        Autoencoder
      |                      |
      +----------+-----------+
                 |
                 v
          Trained ML Models
                 |
                 v
        Python Kafka Producer
                 |
                 v
              Kafka
       Topic: fraud-transactions
                 |
                 v
             Cassandra

             Technologies Used
Python
Pandas
Scikit-learn
Isolation Forest
Autoencoder using MLPRegressor
Kafka
Cassandra
Docker
Joblib
PaySim Dataset
Dataset

The project uses the PaySim financial transaction dataset.

Dataset source:

Kaggle - PaySim 1

The dataset contains approximately 6.36 million transactions with the following fields:

step
type
amount
nameOrig
oldbalanceOrg
newbalanceOrig
nameDest
oldbalanceDest
newbalanceDest
isFraud
isFlaggedFraud

The raw dataset is stored locally and is excluded from Git because of its large file size.

Week 1 - Infrastructure & Data Simulation
Kafka

Kafka is used as the transaction streaming platform.

Kafka Configuration
Kafka version: 4.3.1
Broker: localhost:9092
Topic: fraud-transactions

The Python producer reads PaySim transactions and publishes them as JSON messages to Kafka.

Example flow:

PaySim CSV
    |
    v
Python Producer
    |
    v
Kafka
    |
    v
fraud-transactions

Kafka message delivery has been tested successfully with PaySim transactions.

Cassandra

Cassandra is used as the transaction storage layer.

Cassandra Configuration
Cassandra version: 4.1
Port: 9042
Keyspace: fraud_detection
Table: transactions

The Cassandra table stores:

Transaction ID
Step
Transaction type
Amount
Origin account
Origin balances
Destination account
Destination balances
Fraud label
Flagged fraud status

Python connectivity with Cassandra has been implemented and tested successfully.

Python Producer

The Python producer:

Reads transactions from the PaySim dataset.
Converts each transaction into a JSON-compatible format.
Sends the transaction to Kafka.
Stores the transaction in Cassandra.
Continues streaming transactions with a small delay to simulate real-time processing.

The producer has been tested with 100 PaySim transactions successfully.

Machine Learning
Feature Engineering

The fraud detection models use transaction and balance-related features.

Numerical Features
amount
oldbalanceOrg
newbalanceOrig
oldbalanceDest
newbalanceDest
Derived Features
origin_balance_change
destination_balance_change
amount_to_origin_balance
amount_to_destination_balance
origin_difference
destination_difference

Transaction type is also encoded using one-hot encoding.

The final feature representation contains 16 features.

Isolation Forest

Isolation Forest was implemented as an unsupervised anomaly detection baseline.

Configuration:

n_estimators = 100
contamination = 0.0013
random_state = 42

The model was trained without using the fraud labels.

The Isolation Forest model was evaluated on the PaySim test data and used as the initial anomaly detection baseline.

Autoencoder

An Autoencoder-based anomaly detection model was also implemented.

The model was trained primarily on normal transactions so that unusual transactions could be identified using reconstruction error.

Architecture:

Input
  |
  v
32 neurons
  |
  v
16 neurons
  |
  v
32 neurons
  |
  v
Output

The model uses:

StandardScaler
One-hot encoding for transaction type
MLPRegressor
Adam optimizer
ReLU activation

The trained model is saved as:

src/autoencoder_model.pkl
Autoencoder Evaluation

The anomaly threshold was selected using validation data based on the F1 score.

Selected threshold:

0.04557055612619186

Final test-set results:

Metric	Result
Precision	48%
Recall	36%
F1 Score	41%

Confusion matrix:

                 Predicted
                Normal  Fraud

Actual Normal   1270239   642
Actual Fraud       1049   594

Therefore:

True Negatives: 1,270,239
False Positives: 642
False Negatives: 1,049
True Positives: 594

Because fraud transactions are highly imbalanced in the PaySim dataset, fraud-class precision, recall and F1 score are more informative than overall accuracy.

Current Implementation Status
Completed
 PaySim dataset integration
 Python data loader
 Feature engineering
 Isolation Forest model
 Autoencoder model
 Model evaluation
 Threshold tuning
 Model serialization
 Docker environment
 Kafka broker
 Kafka topic
 Python Kafka producer
 Cassandra setup
 Cassandra keyspace
 Cassandra transaction table
 Python-Cassandra connection
 PaySim transaction storage in Cassandra
 Kafka transaction streaming
