# Retrieval metadata rules

For current regulatory questions:
1. Prefer `primary_regulatory`.
2. Use `secondary_analysis` as context.
3. Exclude/down-rank `historical_reference` unless historical comparison is requested.

For investigation queries:
- retrieve relevant regulatory/investigation knowledge here;
- retrieve account-specific transactions and alerts from Cassandra separately;
- combine the two in the RAG context builder.

Vector retrieval must not be treated as a fraud verdict.
