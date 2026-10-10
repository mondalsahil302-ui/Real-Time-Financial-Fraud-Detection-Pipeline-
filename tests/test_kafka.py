import pytest
from kafka import KafkaProducer


def test_kafka_raw_connection():
    try:
        producer = KafkaProducer(bootstrap_servers="localhost:9092", request_timeout_ms=1000)
        producer.close()
    except Exception as exc:
        pytest.skip(f"Kafka service is not running on port 9092: {exc}")


if __name__ == "__main__":
    producer = KafkaProducer(bootstrap_servers="localhost:9092")
    print("Kafka connection successful!")
    producer.close()
