import argparse
import csv
import json
import time
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer


# --------------------------------------------------
# Configuration
# --------------------------------------------------

CSV_FILE = r".\data\PS_20174392719_1491204439457_log.csv"
KAFKA_SERVER = "localhost:9092"
TOPIC = "transactions"


# --------------------------------------------------
# Command-line arguments
# --------------------------------------------------

parser = argparse.ArgumentParser(
    description="Stream PaySim transactions to Kafka"
)

parser.add_argument(
    "--max-transactions",
    type=int,
    default=10,
    help="Maximum number of transactions to send"
)

parser.add_argument(
    "--delay",
    type=float,
    default=0.1,
    help="Delay between transactions in seconds"
)

args = parser.parse_args()


# --------------------------------------------------
# Basic validation
# --------------------------------------------------

if args.max_transactions <= 0:
    raise ValueError("--max-transactions must be greater than 0")

if args.delay < 0:
    raise ValueError("--delay cannot be negative")


# --------------------------------------------------
# Create Kafka Producer
# --------------------------------------------------

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda value: json.dumps(value).encode("utf-8")
)

print("Kafka producer started...")
print(f"Kafka server: {KAFKA_SERVER}")
print(f"Topic: {TOPIC}")
print(f"Maximum transactions: {args.max_transactions}")
print(f"Delay: {args.delay} seconds")
print()


# --------------------------------------------------
# Read PaySim dataset and stream transactions
# --------------------------------------------------

sent_count = 0

try:
    with open(CSV_FILE, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for count, row in enumerate(reader, start=1):

            # Create a unique transaction ID
            transaction_id = str(uuid.uuid4())

            # Create the time when our simulator generates the event
            event_time = datetime.now(timezone.utc).isoformat()

            # Build the Kafka transaction message
            transaction = {
                "transaction_id": transaction_id,
                "event_time": event_time,

                "step": int(row["step"]),
                "type": row["type"],
                "amount": float(row["amount"]),

                "nameOrig": row["nameOrig"],
                "oldbalanceOrg": float(row["oldbalanceOrg"]),
                "newbalanceOrig": float(row["newbalanceOrig"]),

                "nameDest": row["nameDest"],
                "oldbalanceDest": float(row["oldbalanceDest"]),
                "newbalanceDest": float(row["newbalanceDest"]),

                # Ground-truth fields from PaySim.
                # These are kept for testing/evaluation.
                # Do NOT use isFraud as a model input later.
                "isFraud": int(row["isFraud"]),
                "isFlaggedFraud": int(row["isFlaggedFraud"])
            }

            # Send transaction to Kafka
            producer.send(
                TOPIC,
                value=transaction
            )

            sent_count += 1

            print(
                f"Sent {sent_count}: "
                f"{transaction['transaction_id']} | "
                f"{transaction['type']} | "
                f"{transaction['amount']}"
            )

            # Simulate real-time arrival
            time.sleep(args.delay)

            # Stop after the requested number of transactions
            if sent_count >= args.max_transactions:
                break

except FileNotFoundError:
    print(f"ERROR: PaySim CSV not found: {CSV_FILE}")
    raise

except KeyError as error:
    print(f"ERROR: Missing expected PaySim column: {error}")
    raise

except ValueError as error:
    print(f"ERROR: Invalid value in PaySim dataset: {error}")
    raise

finally:
    # Make sure all pending Kafka messages are delivered
    producer.flush()
    producer.close()


# --------------------------------------------------
# Completion message
# --------------------------------------------------

print()
print(f"Producer finished. {sent_count} transactions sent.")