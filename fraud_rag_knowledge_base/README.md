# Fraud RAG Knowledge Base v2

## Structure

```text
01_rbi_2024_master_direction
02_early_warning_signals_ews_rfa
03_transaction_monitoring_and_analytics
04_fraud_classification
05_investigation
06_governance_accountability_controls
07_reporting
08_fraud_case_lifecycle
09_cheque_related_fraud
10_digital_banking_and_payment_fraud
11_physical_security_incidents
12_other_rbi_fraud_risk_topics
```

## RAG data flow

```text
Current Alert
    +
Cassandra Account History
    +
Retrieved Knowledge from this folder
    ↓
Investigation Context
    ↓
Future LLM
```

The knowledge base does not replace Cassandra and does not contain raw customer transaction history.
