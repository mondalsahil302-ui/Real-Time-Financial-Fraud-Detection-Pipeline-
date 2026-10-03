CREATE KEYSPACE IF NOT EXISTS fraud_detection
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS transactions (
    name_orig text,
    event_time timestamp,
    transaction_id text,
    event_date date,
    event_hour int,
    transaction_type text,
    name_dest text,
    amount double,
    old_balance_orig double,
    new_balance_orig double,
    old_balance_dest double,
    new_balance_dest double,
    anomaly_score double,
    risk_level text,
    risk_action text,
    xgboost_probability double,
    xgboost_prediction boolean,
    final_prediction boolean,
    final_decision_path text,
    model_version text,
    source text,
    inserted_at timestamp,
    PRIMARY KEY ((name_orig), event_time, transaction_id)
) WITH CLUSTERING ORDER BY (event_time DESC, transaction_id ASC);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    name_orig text,
    event_time timestamp,
    alert_id text,
    transaction_id text,
    event_date date,
    event_hour int,
    transaction_type text,
    name_dest text,
    amount double,
    old_balance_orig double,
    new_balance_orig double,
    old_balance_dest double,
    new_balance_dest double,
    anomaly_score double,
    risk_level text,
    risk_action text,
    alert_required boolean,
    xgboost_probability double,
    xgboost_prediction boolean,
    final_prediction boolean,
    final_decision_path text,
    final_risk_action text,
    model_version text,
    status text,
    created_at timestamp,
    PRIMARY KEY ((name_orig), event_time, alert_id)
) WITH CLUSTERING ORDER BY (event_time DESC, alert_id ASC);

CREATE TABLE IF NOT EXISTS investigation_results (
    alert_id text,
    generated_at timestamp,
    investigation_id text,
    transaction_id text,
    retrieved_context text,
    retrieved_documents text,
    retrieval_count int,
    llm_explanation text,
    investigation_summary text,
    risk_reasoning text,
    recommended_review_points text,
    investigation_status text,
    llm_model text,
    rag_version text,
    PRIMARY KEY ((alert_id), generated_at, investigation_id)
) WITH CLUSTERING ORDER BY (generated_at DESC, investigation_id ASC);
