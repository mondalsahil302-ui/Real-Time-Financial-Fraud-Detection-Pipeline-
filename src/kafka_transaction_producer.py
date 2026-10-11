
import argparse
import json
import time
import uuid

import pandas as pd
from kafka import KafkaProducer
from cassandra.cluster import Cluster


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
KAFKA_SERVER = "localhost:9092"
TOPIC = "fraud-transactions"
CASSANDRA_HOST = "localhost"
CASSANDRA_PORT = 9042
KEYSPACE = "fraud_detection"


INSERT_QUERY = """
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


def create_producer():
    """Create a Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=KAFKA_SERVER,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )


def create_cassandra_session():
    """Connect to Cassandra and prepare the INSERT query once."""
    cluster = Cluster(
        [CASSANDRA_HOST],
        port=CASSANDRA_PORT,
    )

    try:
        session = cluster.connect(KEYSPACE)
        prepared_statement = session.prepare(INSERT_QUERY)

        print("Connected to Cassandra successfully!")
        print("Cassandra INSERT statement prepared.")

        return cluster, session, prepared_statement

    except Exception:
        cluster.shutdown()
        raise


def insert_transaction(session, prepared_statement, transaction):
    """Store one transaction in Cassandra using the prepared statement."""
    session.execute(
        prepared_statement,
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


def stream_transactions(
    producer,
    session,
    prepared_statement,
    limit=100,
):
    """Read PaySim transactions, send them to Kafka, and store them in Cassandra."""

    df = pd.read_csv(DATA_PATH, nrows=limit)

    if df.empty:
        print("No transactions found in the dataset.")
        return

    processed_count = 0

    for _, row in df.iterrows():
        transaction = row.to_dict()

        # Send transaction to Kafka and wait for acknowledgement.
        future = producer.send(TOPIC, value=transaction)
        future.get(timeout=10)

        # Store transaction in Cassandra.
        insert_transaction(
            session,
            prepared_statement,
            transaction,
        )

        processed_count += 1

        print(
            f"Processed: {transaction['type']} | "
            f"Amount: {transaction['amount']} | "
            f"Fraud: {transaction['isFraud']}"
        )

        time.sleep(0.1)

    producer.flush()

    print(f"\nSuccessfully processed {processed_count} transactions.")


def main():
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

    if args.limit <= 0:
        parser.error("--limit must be greater than zero.")

    producer = None
    cluster = None

    try:
        producer = create_producer()

        cluster, session, prepared_statement = (
            create_cassandra_session()
        )

        stream_transactions(
            producer,
            session,
            prepared_statement,
            limit=args.limit,
        )

        print("Transaction streaming completed.")

    finally:
        if producer is not None:
            producer.close()

        if cluster is not None:
            cluster.shutdown()


if __name__ == "__main__":
    main()