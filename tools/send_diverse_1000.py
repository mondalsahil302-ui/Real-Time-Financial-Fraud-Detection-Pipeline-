from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from kafka import KafkaProducer


# ============================================================
# PROJECT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# CONFIG
# ============================================================

DATASET_PATH = Path(
    os.getenv(
        "DATASET_PATH",
        "./data/PS_20174392719_1491204439457_log.csv",
    )
)

KAFKA_SERVER = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)

TOPIC = os.getenv(
    "TRANSACTIONS_TOPIC",
    "transactions",
)

RANDOM_SEED = 42

# ------------------------------------------------------------
# IMPORTANT:
#
# Your final IF experiment used:
#
# first 500,000 rows
# chronological ordering
# 60% train
# 20% validation
# 20% test
#
# Therefore:
#
# test starts at row 400,000
# test ends at row 500,000
# ------------------------------------------------------------

EXPERIMENT_ROWS = 500_000
TRAIN_END = 300_000
VALIDATION_END = 400_000
TEST_END = 500_000


# ============================================================
# COMMAND LINE
# ============================================================

if len(sys.argv) > 1:
    TEST_ROWS_TO_SEND = int(sys.argv[1])
else:
    TEST_ROWS_TO_SEND = 1_000

if TEST_ROWS_TO_SEND <= 0:
    raise ValueError(
        "Number of test rows must be greater than zero."
    )

if TEST_ROWS_TO_SEND > 100_000:
    raise ValueError(
        "The frozen PaySim test split contains 100,000 rows."
    )


# ============================================================
# VALIDATION
# ============================================================

if not DATASET_PATH.exists():
    raise FileNotFoundError(
        f"PaySim dataset not found: {DATASET_PATH}"
    )


# ============================================================
# LOAD EXACT EXPERIMENT DATA
# ============================================================

print("=" * 70)
print("PAYSIM HELD-OUT TEST STREAM")
print("=" * 70)

print(f"Dataset       : {DATASET_PATH}")
print(f"Experiment    : first {EXPERIMENT_ROWS:,} rows")
print("Split         : chronological 60/20/20")
print(f"Test range    : rows {VALIDATION_END:,} - {TEST_END:,}")
print(f"Rows to send  : {TEST_ROWS_TO_SEND:,}")
print()


required_columns = [
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
]


df = pd.read_csv(
    DATASET_PATH,
    nrows=EXPERIMENT_ROWS,
    usecols=required_columns,
    low_memory=False,
)


if len(df) != EXPERIMENT_ROWS:
    raise ValueError(
        f"Expected {EXPERIMENT_ROWS:,} rows, "
        f"but loaded {len(df):,}."
    )


# ============================================================
# REPRODUCE TRAINING ORDER
# ============================================================

df["_source_order"] = range(len(df))

df = (
    df
    .sort_values(
        ["step", "_source_order"],
        kind="stable",
    )
    .reset_index(drop=True)
)


# ============================================================
# EXACT HELD-OUT TEST SPLIT
# ============================================================

test_df = (
    df.iloc[
        VALIDATION_END:TEST_END
    ]
    .copy()
    .reset_index(drop=True)
)


if len(test_df) != 100_000:
    raise ValueError(
        "Frozen test split is not exactly 100,000 rows."
    )


# ============================================================
# OPTIONAL SUBSET
# ============================================================

test_df = test_df.iloc[
    :TEST_ROWS_TO_SEND
].copy()


# ============================================================
# TEST SUMMARY
# ============================================================

print("=" * 70)
print("TEST DATA SUMMARY")
print("=" * 70)

print(
    f"Selected rows : {len(test_df):,}"
)

print(
    f"Fraud rows    : "
    f"{int(test_df['isFraud'].sum()):,}"
)

print(
    f"Normal rows   : "
    f"{int((test_df['isFraud'] == 0).sum()):,}"
)

print()
print("Transaction types:")
print(
    test_df["type"]
    .value_counts()
    .to_string()
)

print()
print("Amount statistics:")
print(
    test_df["amount"]
    .describe()
    .to_string()
)

print()
print("Fraud rate:")
print(
    f"{test_df['isFraud'].mean() * 100:.4f}%"
)

print("=" * 70)
print()


# ============================================================
# KAFKA PRODUCER
# ============================================================

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,

    key_serializer=lambda key: (
        key.encode("utf-8")
        if key is not None
        else None
    ),

    value_serializer=lambda value: (
        json.dumps(value)
        .encode("utf-8")
    ),

    acks="all",
    retries=5,

    delivery_timeout_ms=30_000,
    request_timeout_ms=10_000,

    linger_ms=5,
    batch_size=32 * 1024,
    compression_type="gzip",
)


# ============================================================
# SEND
# ============================================================

print("=" * 70)
print("SENDING PAYSIM TEST DATA")
print("=" * 70)

sent = 0

try:

    for _, row in test_df.iterrows():

        transaction_id = str(
            uuid.uuid4()
        )

        event_time = datetime.now(
            timezone.utc
        ).isoformat()

        transaction = {
            "transaction_id": transaction_id,

            "event_time": event_time,

            "source": "paysim_test",

            "step": int(
                row["step"]
            ),

            "event_step": int(
                row["step"]
            ),

            "type": str(
                row["type"]
            ),

            "amount": float(
                row["amount"]
            ),

            "nameOrig": str(
                row["nameOrig"]
            ),

            "oldbalanceOrg": float(
                row["oldbalanceOrg"]
            ),

            "newbalanceOrig": float(
                row["newbalanceOrig"]
            ),

            "nameDest": str(
                row["nameDest"]
            ),

            "oldbalanceDest": float(
                row["oldbalanceDest"]
            ),

            "newbalanceDest": float(
                row["newbalanceDest"]
            ),

            # Evaluation-only fields.
            # Spark models must NOT use these.
            "isFraud": int(
                row["isFraud"]
            ),

            "isFlaggedFraud": int(
                row["isFlaggedFraud"]
            ),
        }

        future = producer.send(
            TOPIC,
            key=str(row["nameOrig"]),
            value=transaction,
        )

        metadata = future.get(
            timeout=35
        )

        sent += 1

        print(
            f"Sent {sent:6d}/{len(test_df):6d} | "
            f"step={transaction['step']:4d} | "
            f"type={transaction['type']:<9} | "
            f"amount={transaction['amount']:<14.2f} | "
            f"actual_fraud={transaction['isFraud']} | "
            f"partition={metadata.partition} | "
            f"offset={metadata.offset}"
        )

        # Real-time simulation.
        time.sleep(0.05)


finally:

    print()
    print(
        "Flushing remaining Kafka messages..."
    )

    producer.flush()
    producer.close()


print()
print("=" * 70)
print("PAYSIM TEST STREAM FINISHED")
print("=" * 70)
print(
    f"Total transactions sent: {sent:,}"
)
print(
    f"Actual fraud: "
    f"{int(test_df['isFraud'].sum()):,}"
)
print(
    f"Actual normal: "
    f"{int((test_df['isFraud'] == 0).sum()):,}"
)
print("=" * 70)