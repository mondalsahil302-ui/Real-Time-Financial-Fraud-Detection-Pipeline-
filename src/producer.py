import json
import time

import pandas as pd
from kafka import KafkaProducer


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
KAFKA_SERVER = "localhost:9092"
TOPIC = "fraud-transactions"


def create_producer():
    return KafkaProducer(
        bootstrap_servers=KAFKA_SERVER,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )


def stream_transactions(producer, limit=100):
    """Read PaySim transactions and send them to Kafka."""
    df = pd.read_csv(DATA_PATH, nrows=limit)

    for _, row in df.iterrows():
        transaction = row.to_dict()

        producer.send(TOPIC, value=transaction)
        print(f"Sent transaction: {transaction['type']} | Amount: {transaction['amount']}")

        time.sleep(0.1)

    producer.flush()


if __name__ == "__main__":
    producer = create_producer()

    try:
        stream_transactions(producer, limit=100)
        print("Transaction streaming completed.")
    finally:
        producer.close()