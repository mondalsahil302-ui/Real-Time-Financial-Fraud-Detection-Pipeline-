from cassandra.cluster import Cluster


def get_cassandra_session():
    cluster = Cluster(["localhost"], port=9042)

    session = cluster.connect("fraud_detection")

    print("Connected to Cassandra successfully!")

    return cluster, session


if __name__ == "__main__":
    cluster, session = get_cassandra_session()

    cluster.shutdown()