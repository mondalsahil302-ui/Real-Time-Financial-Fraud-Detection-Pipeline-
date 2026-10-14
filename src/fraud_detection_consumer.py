
import json
import logging

import joblib
import numpy as np
import pandas as pd
from kafka import KafkaConsumer, KafkaProducer

from cassandra_connection import get_cassandra_session


# -------------------- CONFIGURATION --------------------

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
INPUT_TOPIC = "fraud-transactions"
ALERT_TOPIC = "fraud-alerts"
LOW_RISK_TOPIC = "low-risk-transactions"

ISOLATION_FOREST_PATH = "src/isolation_forest_model.pkl"
AUTOENCODER_PATH = "src/autoencoder_model.pkl"

KEYSPACE = "fraud_detection"
TABLE = "transactions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# -------------------- FEATURE ENGINEERING --------------------

def create_features(transaction):
    """Create the same 11 numerical features used during training."""

    amount = float(transaction.get("amount", 0) or 0)
    old_origin = float(transaction.get("oldbalanceOrg", 0) or 0)
    new_origin = float(transaction.get("newbalanceOrig", 0) or 0)
    old_dest = float(transaction.get("oldbalanceDest", 0) or 0)
    new_dest = float(transaction.get("newbalanceDest", 0) or 0)

    features = {
        "amount": amount,
        "oldbalanceOrg": old_origin,
        "newbalanceOrig": new_origin,
        "oldbalanceDest": old_dest,
        "newbalanceDest": new_dest,
        "origin_balance_change": old_origin - new_origin,
        "destination_balance_change": new_dest - old_dest,
        "amount_to_origin_balance": amount / (old_origin + 1),
        "amount_to_destination_balance": amount / (old_dest + 1),
        "origin_difference": amount - (old_origin - new_origin),
        "destination_difference": amount - (new_dest - old_dest),
    }

    return (
        pd.DataFrame([features])
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
    )


def prepare_features(transaction, encoder):
    """Build features in the exact order used during training."""

    numeric = create_features(transaction)

    type_frame = pd.DataFrame({
        "type": [str(transaction.get("type", ""))]
    })

    encoded_values = encoder.transform(type_frame)

    encoded = pd.DataFrame(
        encoded_values,
        columns=encoder.get_feature_names_out(["type"]),
    )

    features = pd.concat(
        [numeric.reset_index(drop=True), encoded.reset_index(drop=True)],
        axis=1,
    )

    expected_order = list(numeric.columns) + list(
        encoder.get_feature_names_out(["type"])
    )

    return features.reindex(columns=expected_order, fill_value=0)


# -------------------- DATABASE SETUP --------------------

def ensure_prediction_columns(session):
    """Add prediction fields without deleting existing table data."""

    columns_to_add = {
        "predicted_is_fraud": "int",
        "isolation_forest_anomaly": "int",
        "autoencoder_anomaly": "int",
        "reconstruction_error": "double",
        "risk_level": "text",
    }

    result = session.execute(
        """
        SELECT column_name
        FROM system_schema.columns
        WHERE keyspace_name = %s AND table_name = %s
        """,
        (KEYSPACE, TABLE),
    )

    existing_columns = {row.column_name for row in result}

    for column, data_type in columns_to_add.items():
        if column not in existing_columns:
            session.execute(
                f"ALTER TABLE {TABLE} ADD {column} {data_type}"
            )
            logger.info("Added Cassandra column: %s", column)


# -------------------- MAIN PIPELINE --------------------

def main():
    logger.info("Loading trained models...")

    isolation_package = joblib.load(ISOLATION_FOREST_PATH)
    autoencoder_package = joblib.load(AUTOENCODER_PATH)

    isolation_model = isolation_package["model"]
    isolation_encoder = isolation_package["encoder"]

    autoencoder_model = autoencoder_package["model"]
    autoencoder_encoder = autoencoder_package["encoder"]
    scaler = autoencoder_package["scaler"]
    threshold = float(autoencoder_package["threshold"])

    if isolation_model.n_features_in_ != 16:
        raise ValueError("Isolation Forest must expect 16 features.")

    if autoencoder_model.n_features_in_ != 16:
        raise ValueError("Autoencoder must expect 16 features.")

    if list(isolation_encoder.categories_[0]) != list(
        autoencoder_encoder.categories_[0]
    ):
        raise ValueError("The two models use different transaction types.")

    logger.info("Both models loaded successfully.")

    cluster, session = get_cassandra_session()
    consumer = None
    producer = None

    try:
        ensure_prediction_columns(session)

        insert_query = session.prepare(
            """
            INSERT INTO transactions (
                transaction_id, amount, is_flagged_fraud, is_fraud,
                name_dest, name_orig, new_balance_dest, new_balance_orig,
                old_balance_dest, old_balance_org, step, type,
                predicted_is_fraud, isolation_forest_anomaly,
                autoencoder_anomaly, reconstruction_error, risk_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )

        consumer = KafkaConsumer(
            INPUT_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda value: json.loads(
                value.decode("utf-8")
            ),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            group_id="fraud-detection-consumer-v1",
        )

        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda value: json.dumps(
                value
            ).encode("utf-8"),
        )

        logger.info("Listening to topic: %s", INPUT_TOPIC)

        for message in consumer:
            try:
                transaction = message.value

                isolation_features = prepare_features(
                    transaction, isolation_encoder
                )
                autoencoder_features = prepare_features(
                    transaction, autoencoder_encoder
                )

                # Model 1: Isolation Forest anomaly detection.
                isolation_anomaly = (
                    int(isolation_model.predict(isolation_features)[0]) == -1
                )

                # Model 2: Autoencoder reconstruction error.
                scaled_features = scaler.transform(autoencoder_features)
                reconstructed = autoencoder_model.predict(scaled_features)

                reconstruction_error = float(
                    np.mean((scaled_features - reconstructed) ** 2)
                )

                autoencoder_anomaly = reconstruction_error > threshold

                predicted_fraud = int(
                    isolation_anomaly or autoencoder_anomaly
                )

                if isolation_anomaly and autoencoder_anomaly:
                    risk_level = "HIGH"
                elif predicted_fraud:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "LOW"

                # Stable ID prevents duplicate rows when replaying a
                # message from the same Kafka partition and offset.
                transaction_id = (
                    f"{message.topic}-{message.partition}-{message.offset}"
                )

                # Preserve the dataset's actual labels separately.
                actual_fraud = int(transaction.get("isFraud", 0) or 0)
                actual_flagged = int(
                    transaction.get("isFlaggedFraud", 0) or 0
                )

                amount = float(transaction.get("amount", 0) or 0)
                step = int(transaction.get("step", 0) or 0)

                session.execute(
                    insert_query,
                    (
                        transaction_id,
                        amount,
                        actual_flagged,
                        actual_fraud,
                        str(transaction.get("nameDest", "")),
                        str(transaction.get("nameOrig", "")),
                        float(transaction.get("newbalanceDest", 0) or 0),
                        float(transaction.get("newbalanceOrig", 0) or 0),
                        float(transaction.get("oldbalanceDest", 0) or 0),
                        float(transaction.get("oldbalanceOrg", 0) or 0),
                        step,
                        str(transaction.get("type", "")),
                        predicted_fraud,
                        int(isolation_anomaly),
                        int(autoencoder_anomaly),
                        reconstruction_error,
                        risk_level,
                    ),
                )

                result_event = {
                    "transaction_id": transaction_id,
                    "amount": amount,
                    "type": str(transaction.get("type", "")),
                    "predicted_is_fraud": predicted_fraud,
                    "risk_level": risk_level,
                    "isolation_forest_anomaly": isolation_anomaly,
                    "autoencoder_anomaly": autoencoder_anomaly,
                    "reconstruction_error": reconstruction_error,
                    "threshold": threshold,
                    "actual_is_fraud": actual_fraud,
                }

                # Publish the result before committing the input offset.
                target_topic = (
                    ALERT_TOPIC if predicted_fraud else LOW_RISK_TOPIC
                )
                producer.send(
                    target_topic, value=result_event
                ).get(timeout=10)

                consumer.commit()

                if predicted_fraud:
                    logger.warning("FRAUD ALERT: %s", result_event)
                else:
                    logger.info(
                        "LOW RISK: transaction_id=%s amount=%.2f",
                        transaction_id,
                        amount,
                    )

            except Exception:
                logger.exception(
                    "Failed to process Kafka message at offset %s",
                    message.offset,
                )
                # Leave this message uncommitted so it can be retried.
                raise

    except KeyboardInterrupt:
        logger.info("Stopping fraud detection consumer...")

    finally:
        if consumer is not None:
            consumer.close()

        if producer is not None:
            producer.flush()
            producer.close()

        cluster.shutdown()
        logger.info("Consumer resources closed.")


if __name__ == "__main__":
    main()
