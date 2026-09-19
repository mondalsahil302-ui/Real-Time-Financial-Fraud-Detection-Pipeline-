import csv
import json
import time
from kafka import KafkaProducer

CSV_FILE = r".\data\PS_20174392719_1491204439457_log.csv"
KAFKA_SERVER = "localhost:9092"
TOPIC = "transactions"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8")
)

print("Kafka producer started...")

with open(CSV_FILE, "r", encoding="utf-8") as file:
    reader = csv.DictReader(file)

    for count, row in enumerate(reader, start=1):
        transaction = {
            "step": int(row["step"]),
            "type": row["type"],
            "amount": float(row["amount"]),
            "nameOrig": row["nameOrig"],
            "oldbalanceOrg": float(row["oldbalanceOrg"]),
            "newbalanceOrig": float(row["newbalanceOrig"]),
            "nameDest": row["nameDest"],
            "oldbalanceDest": float(row["oldbalanceDest"]),
            "newbalanceDest": float(row["newbalanceDest"]),
            "isFraud": int(row["isFraud"]),
            "isFlaggedFraud": int(row["isFlaggedFraud"])
        }

        producer.send(TOPIC, value=transaction)

        print(
            f"Sent: {transaction['nameOrig']} → "
            f"{transaction['nameDest']} | "
            f"{transaction['type']} | "
            f"{transaction['amount']}"
        )

        time.sleep(0.1)

        if count == 10:
            break