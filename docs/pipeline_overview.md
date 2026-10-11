# Pipeline Overview

## Project Flow

The Real-Time Financial Fraud Detection Pipeline is designed to identify potentially fraudulent financial transactions using machine learning and streaming technologies.



### Current Pipeline



PaySim Dataset

|

v

Data Preprocessing

|

v

Feature Engineering

|

v

Isolation Forest / Autoencoder

|

v

Model Evaluation

|

v

Saved Model



### Transaction Streaming

Incoming Transactions

|

v

Python Kafka Producer

|

v

Kafka

|

v

Cassandra



Machine Learning

Two anomaly-detection approaches were implemented:

* Isolation Forest — baseline model
* Autoencoder — primary experimental approach

The models were evaluated using precision, recall, and F1-score because the PaySim dataset is highly imbalanced.



## Current Implementation

The following components are currently implemented:

* PaySim data loading
* Feature engineering
* Isolation Forest training and evaluation
* Autoencoder training and evaluation
* Model serialization
* Kafka transaction streaming
* Cassandra transaction storage



## Future Pipeline Components

The next phase will extend the pipeline with:

* Spark Structured Streaming
* Real-time model inference
* Fraud alert processing
* Grafana monitoring
* Prometheus metrics

