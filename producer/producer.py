"""Reusable PaySim Kafka producer; importing this module has no side effects."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable, Iterable, Mapping

from dotenv import load_dotenv
from kafka import KafkaProducer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.metrics import DURATION, count as metric_count, start_metrics_server

load_dotenv(PROJECT_ROOT / ".env")

CSV_FILE = os.getenv("DATASET_PATH", str(PROJECT_ROOT / "data" / "PS_20174392719_1491204439457_log.csv"))
KAFKA_SERVER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("TRANSACTIONS_TOPIC", "transactions")
SOURCE = "paysim"


@dataclass
class ProducerResult:
    generated_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    cancelled: bool = False


def build_transaction(row: Mapping[str, object], *, source: str = SOURCE,
                      batch_id: str | None = None, producer_sequence: int | None = None) -> dict:
    """Map a PaySim row or validated manual event onto the existing Kafka schema."""
    current_time = datetime.now(timezone.utc).isoformat()
    if "step" in row:
        step = int(row["step"])
        tx = {
            "step": step,
            "event_step": int(row.get("event_step", step) or step),
            "type": str(row["type"]),
            "amount": float(row["amount"]),
            "nameOrig": str(row["nameOrig"]),
            "oldbalanceOrg": float(row["oldbalanceOrg"]),
            "newbalanceOrig": float(row["newbalanceOrig"]),
            "nameDest": str(row["nameDest"]),
            "oldbalanceDest": float(row["oldbalanceDest"]),
            "newbalanceDest": float(row["newbalanceDest"]),
        }
        for optional in ("isFraud", "isFlaggedFraud"):
            if row.get(optional) is not None:
                tx[optional] = int(row[optional])
    else:
        raise ValueError("transaction requires the existing PaySim 'step' field")
    tx.update({
        "transaction_id": str(row.get("transaction_id") or f"TXN-{uuid.uuid4()}"),
        "event_time": str(row.get("event_time") or current_time),
        "source": source,
    })
    if batch_id:
        tx["batch_id"] = batch_id
    if producer_sequence is not None:
        tx["producer_sequence"] = int(producer_sequence)
    return tx


def _make_producer(producer_factory=None):
    factory = producer_factory or KafkaProducer
    return factory(
        bootstrap_servers=KAFKA_SERVER,
        key_serializer=lambda key: key.encode("utf-8"),
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        acks="all", retries=5, delivery_timeout_ms=30_000, request_timeout_ms=10_000,
        linger_ms=5, batch_size=32 * 1024, compression_type="gzip",
    )


def produce_batch(transaction_count: int, delay: float = 0.1, *, source: str = SOURCE,
                  batch_id: str | None = None, transactions: Iterable[Mapping[str, object]] | None = None,
                  cancel_event: Event | None = None,
                  on_generated: Callable[[dict, int], None] | None = None,
                  on_sent: Callable[[dict, object], None] | None = None,
                  on_failed: Callable[[dict | None, Exception], None] | None = None,
                  producer_factory=None, sleep: Callable[[float], None] = time.sleep,
                  serve_metrics: bool = True, continue_on_error: bool = True,
                  output=print) -> ProducerResult:
    """Produce PaySim rows (or validated supplied events) using the CLI's real Kafka path."""
    if transaction_count <= 0:
        raise ValueError("transaction_count must be greater than 0")
    if delay < 0:
        raise ValueError("delay cannot be negative")
    dataset = Path(CSV_FILE)
    if transactions is None and not dataset.exists():
        raise FileNotFoundError(f"PaySim CSV not found: {dataset}")
    if serve_metrics:
        start_metrics_server(port=int(os.getenv("PRODUCER_METRICS_PORT", "8003")))

    result = ProducerResult()
    producer = _make_producer(producer_factory)
    output("============================================================")
    output("Kafka Transaction Producer")
    output("============================================================")
    output(f"Kafka Server        : {KAFKA_SERVER}")
    output(f"Topic               : {TOPIC}")
    output(f"Dataset             : {dataset if transactions is None else 'validated transaction input'}")
    output(f"Maximum Transactions: {transaction_count}")
    output(f"Delay               : {delay} seconds")
    output("============================================================\n")

    def source_rows():
        if transactions is not None:
            for supplied in transactions:
                yield supplied
            return
        with dataset.open("r", encoding="utf-8", newline="") as source_file:
            reader = csv.DictReader(source_file)
            for row in reader:
                yield row

    try:
        for sequence, row in enumerate(source_rows(), start=1):
            if sequence > transaction_count:
                break
            if cancel_event is not None and cancel_event.is_set():
                result.cancelled = True
                break
            generation_started = time.perf_counter()
            transaction = build_transaction(row, source=source, batch_id=batch_id, producer_sequence=sequence)
            DURATION.labels("producer", "transaction_generation").observe(
                time.perf_counter() - generation_started
            )
            result.generated_count += 1
            if on_generated:
                on_generated(transaction, sequence)
            try:
                future = producer.send(TOPIC, key=transaction["nameOrig"], value=transaction)
                metadata = future.get(timeout=35)
                result.sent_count += 1
                metric_count("kafka", "transaction_produced", "success")
                if on_sent:
                    on_sent(transaction, metadata)
                output(f"Sent {sequence:>4} | TX={transaction['transaction_id']} | Type={transaction['type']:<9} | Amount={transaction['amount']:<12.2f} | Key={transaction['nameOrig']} | Partition={metadata.partition} | Offset={metadata.offset}")
            except Exception as exc:
                result.failed_count += 1
                metric_count("kafka", "transaction_produced", "failure")
                if on_failed:
                    on_failed(transaction, exc)
                output(f"ERROR: Kafka producer failed for {transaction['transaction_id']}: {exc}")
                if not continue_on_error:
                    raise
            if delay:
                sleep(delay)
    except (FileNotFoundError, KeyError, ValueError):
        raise
    finally:
        output("\nFlushing remaining Kafka messages...")
        try:
            producer.flush()
        finally:
            producer.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stream PaySim transactions to Kafka")
    parser.add_argument("--max-transactions", type=int, default=10, help="Maximum number of transactions to send")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between transactions in seconds")
    args = parser.parse_args(argv)
    result = produce_batch(args.max_transactions, args.delay, source=SOURCE, continue_on_error=False)
    print("\n============================================================")
    print("Producer finished.")
    print(f"Total transactions sent: {result.sent_count}")
    print("============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
