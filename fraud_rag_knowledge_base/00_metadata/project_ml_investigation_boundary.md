# Project ML / Investigation Boundary

This is project-specific context, not RBI policy.

The existing system uses machine-learning and risk signals to detect and route transaction alerts.

RAG should use the alert's model outputs as investigation context but must not reinterpret:
- anomaly score as a fraud probability;
- risk level as proof of confirmed fraud;
- retrieval similarity as a legal or fraud conclusion.

Account-specific evidence comes from Cassandra.
Regulatory/investigation knowledge comes from this knowledge base.
The future LLM explains the combined evidence.
