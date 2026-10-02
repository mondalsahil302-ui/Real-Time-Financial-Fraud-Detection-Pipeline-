import argparse
import csv
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from kafka import KafkaProducer


# ============================================================
# Load Environment Variables
# ============================================================

load_dotenv()


# ============================================================
# Configuration
# ============================================================

CSV_FILE = os.getenv(
    "DATASET_PATH",
    "./data/PS_20174392719_1491204439457_log.csv"
)

KAFKA_SERVER = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092"
)

TOPIC = os.getenv(
    "TRANSACTIONS_TOPIC",
    "transactions"
)

SOURCE = "paysim"


# ============================================================
# Command-Line Arguments
# ============================================================

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


# ============================================================
# Basic Validation
# ============================================================

if args.max_transactions <= 0:
    raise ValueError(
        "--max-transactions must be greater than 0"
    )

if args.delay < 0:
    raise ValueError(
        "--delay cannot be negative"
    )


# ============================================================
# Validate Dataset Path
# ============================================================

csv_path = Path(CSV_FILE)

if not csv_path.exists():
    raise FileNotFoundError(
        f"PaySim CSV not found: {csv_path}"
    )


# ============================================================
# Create Kafka Producer
# ============================================================

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,

    # Kafka key serializer
    key_serializer=lambda key: key.encode("utf-8"),

    # JSON value serializer
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),

    # Reliable delivery
    acks="all",
    retries=5,
    delivery_timeout_ms=30_000,
    request_timeout_ms=10_000,

    # Producer batching/compression
    linger_ms=5,
    batch_size=32 * 1024,
    compression_type="gzip"
)


# ============================================================
# Startup Information
# ============================================================

print("=" * 60)
print("Kafka Transaction Producer")
print("=" * 60)

print(f"Kafka Server        : {KAFKA_SERVER}")
print(f"Topic               : {TOPIC}")
print(f"Dataset             : {csv_path}")
print(f"Maximum Transactions: {args.max_transactions}")
print(f"Delay               : {args.delay} seconds")

print("=" * 60)
print()


# ============================================================
# Stream PaySim Transactions
# ============================================================

sent_count = 0

try:

    with csv_path.open(
        "r",
        encoding="utf-8",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        for count, row in enumerate(reader, start=1):

            # ------------------------------------------------
            # Create Unique Transaction ID
            # ------------------------------------------------

            transaction_id = str(uuid.uuid4())


            # ------------------------------------------------
            # Create Event Timestamp
            # ------------------------------------------------

            event_time = datetime.now(
                timezone.utc
            ).isoformat()


            # ------------------------------------------------
            # Build Transaction Event
            # ------------------------------------------------

            transaction = {

                # System metadata
                "transaction_id": transaction_id,
                "event_time": event_time,
                "source": SOURCE,

                # PaySim simulation time
                "step": int(row["step"]),
                "event_step": int(row["step"]),

                # Transaction information
                "type": row["type"],
                "amount": float(row["amount"]),

                # Origin account
                "nameOrig": row["nameOrig"],
                "oldbalanceOrg": float(
                    row["oldbalanceOrg"]
                ),
                "newbalanceOrig": float(
                    row["newbalanceOrig"]
                ),

                # Destination account
                "nameDest": row["nameDest"],
                "oldbalanceDest": float(
                    row["oldbalanceDest"]
                ),
                "newbalanceDest": float(
                    row["newbalanceDest"]
                ),

                # ------------------------------------------------
                # PaySim Ground Truth
                # ------------------------------------------------
                #
                # These fields are retained for offline
                # evaluation/testing.
                #
                # They MUST NOT be used as Isolation Forest
                # model features.
                #
                "isFraud": int(row["isFraud"]),
                "isFlaggedFraud": int(
                    row["isFlaggedFraud"]
                )
            }


            # ------------------------------------------------
            # Kafka Partitioning Key
            # ------------------------------------------------
            #
            # The originating account is used as the key.
            #
            # Kafka uses the key to determine the partition.
            #
            partition_key = row["nameOrig"]


            # ------------------------------------------------
            # Send Transaction to Kafka
            # ------------------------------------------------

            future = producer.send(
                TOPIC,
                key=partition_key,
                value=transaction
            )


            # ------------------------------------------------
            # Wait for Kafka Acknowledgement
            # ------------------------------------------------
            #
            # This confirms that Kafka accepted the record.
            #
            metadata = future.get(timeout=35)


            # ------------------------------------------------
            # Update Counter
            # ------------------------------------------------

            sent_count += 1


            # ------------------------------------------------
            # Display Result
            # ------------------------------------------------

            print(
                f"Sent {sent_count:>4} | "
                f"TX={transaction_id} | "
                f"Type={transaction['type']:<9} | "
                f"Amount={transaction['amount']:<12.2f} | "
                f"Key={partition_key} | "
                f"Partition={metadata.partition} | "
                f"Offset={metadata.offset}"
            )


            # ------------------------------------------------
            # Simulate Real-Time Arrival
            # ------------------------------------------------

            time.sleep(args.delay)


            # ------------------------------------------------
            # Stop After Requested Number
            # ------------------------------------------------

            if sent_count >= args.max_transactions:
                break


except FileNotFoundError as error:

    print(f"ERROR: {error}")
    raise


except KeyError as error:

    print(
        f"ERROR: Missing expected PaySim column: {error}"
    )
    raise


except ValueError as error:

    print(
        f"ERROR: Invalid PaySim value: {error}"
    )
    raise


except Exception as error:

    print(
        f"ERROR: Kafka producer failed: {error}"
    )
    raise


finally:

    # ========================================================
    # Flush Remaining Messages
    # ========================================================

    print()
    print("Flushing remaining Kafka messages...")

    producer.flush()

    producer.close()


# ============================================================
# Completion Message
# ============================================================

print()
print("=" * 60)
print(f"Producer finished.")
print(f"Total transactions sent: {sent_count}")
print("=" * 60)