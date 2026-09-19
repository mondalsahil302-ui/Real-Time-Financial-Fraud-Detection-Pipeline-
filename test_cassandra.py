from cassandra.cluster import Cluster

cluster = Cluster(["127.0.0.1"], port=9042)
session = cluster.connect()

print("Cassandra connection successful!")

cluster.shutdown()