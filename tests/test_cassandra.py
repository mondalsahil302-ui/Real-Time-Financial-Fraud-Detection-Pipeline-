import pytest
from cassandra.cluster import Cluster


def test_cassandra_raw_connection():
    try:
        cluster = Cluster(["127.0.0.1"], port=9042)
        session = cluster.connect()
        cluster.shutdown()
    except Exception as exc:
        pytest.skip(f"Cassandra service is not running on port 9042: {exc}")


if __name__ == "__main__":
    cluster = Cluster(["127.0.0.1"], port=9042)
    session = cluster.connect()
    print("Cassandra connection successful!")
    cluster.shutdown()