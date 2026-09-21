from cassandra.cluster import Cluster


cluster = Cluster(["localhost"], port=9042)
session = cluster.connect("fraud_detection")

query = """
INSERT INTO transactions (
    transaction_id,
    step,
    type,
    amount,
    name_orig,
    old_balance_org,
    new_balance_orig,
    name_dest,
    old_balance_dest,
    new_balance_dest,
    is_fraud,
    is_flagged_fraud
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

prepared = session.prepare(query)

session.execute(
    prepared,
    (
        "TEST001",
        1,
        "PAYMENT",
        100.0,
        "TEST_ORIG",
        500.0,
        400.0,
        "TEST_DEST",
        200.0,
        300.0,
        0,
        0,
    ),
)

print("Test transaction inserted successfully!")

cluster.shutdown()