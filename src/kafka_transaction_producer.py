import json
import time
import uuid
import argparse

import pandas as pd
from kafka import KafkaProducer
from cassandra.cluster import Cluster


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
KAFKA_SERVER = "localhost:9092"
TOPIC = "fraud-transactions"


def create_producer():
    return KafkaProducer(
        bootstrap_servers=KAFKA_SERVER,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )


def create_cassandra_session():
    cluster = Cluster(["localhost"], port=9042)
    session = cluster.connect("fraud_detection")

    print("Connected to Cassandra successfully!")

    return cluster, session


def insert_transaction(session, transaction):
    query = """
    INSERT INTO transactions (
        transaction_id,
        step,
        type,
        amount,
        name_orig,
        old_balance_org,
        new_balance_orig,
        name_dest,
        old_balance_dest,
        new_balance_dest,
        is_fraud,
        is_flagged_fraud
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

   prepared = session.prepare(query)
    session.execute(
        prepared,
        (
            str(uuid.uuid4()),
            int(transaction["step"]),
            str(transaction["type"]),
            float(transaction["amount"]),
            str(transaction["nameOrig"]),
            float(transaction["oldbalanceOrg"]),
            float(transaction["newbalanceOrig"]),
            str(transaction["nameDest"]),
            float(transaction["oldbalanceDest"]),
            float(transaction["newbalanceDest"]),
            int(transaction["isFraud"]),
            int(transaction["isFlaggedFraud"]),
        ),
    )


def stream_transactions(producer, session, limit=100):
    """Read PaySim transactions, send them to Kafka, and store them in Cassandra."""

    df = pd.read_csv(DATA_PATH, nrows=limit)

    for _, row in df.iterrows():
        transaction = row.to_dict()

        # Send transaction to Kafka
        future = producer.send(TOPIC, value=transaction)
        future.get(timeout=10)

        # Store transaction in Cassandra
        insert_transaction(session, transaction)

        print(
            f"Processed: {transaction['type']} | "
            f"Amount: {transaction['amount']} | "
            f"Fraud: {transaction['isFraud']}"
        )

        time.sleep(0.1)

    producer.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stream PaySim transactions to Kafka and Cassandra."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of transactions to stream (default: 100).",
    )
    args = parser.parse_args()

    producer = create_producer()
    cluster, session = create_cassandra_session()

    try:
        stream_transactions(
            producer,
            session,
            limit=args.limit,
        )

        print("Transaction streaming completed.")

    finally:
        producer.close()
        cluster.shutdown()
    return cluster, session
