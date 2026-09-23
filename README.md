# Real-Time Financial Fraud Detection Pipeline

A real-time financial fraud detection pipeline designed to process streaming
mobile-money transactions, detect anomalous behavior, and generate fraud alerts.

## Current Progress

### Week 1
- Apache Kafka provisioned using Docker
- Cassandra provisioned using Docker
- Kafka `transactions` topic created with 3 partitions
- Kafka `fraud-alerts` topic created
- Cassandra `fraud_detection` keyspace created
- Cassandra `transactions` and `fraud_alerts` tables created
- Python environment configured
- PaySim dataset integrated
- Python Kafka producer created
- PaySim transactions successfully streamed to Kafka
- Kafka producer/consumer pipeline tested successfully

## Technology Stack

- Python
- Apache Kafka
- Apache Cassandra
- Docker
- Docker Compose
- PaySim Dataset

## Current Architecture

PaySim Dataset  
↓  
Python Producer  
↓  
Apache Kafka  
↓  
Spark Structured Streaming  
↓  
Fraud Detection Model  
↓  
Cassandra  
↓  
Grafana

## Dataset

PaySim Synthetic Financial Dataset for Fraud Detection.

The dataset contains approximately 6.36 million transaction records and includes
transaction type, amount, sender/receiver balances, and fraud labels.

## Project Status

Week 1 infrastructure and initial streaming pipeline completed.   