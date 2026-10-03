"""Paths and tunable settings for the local RAG vector database."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "fraud_rag_knowledge_base"
PAYSIM_PATH = PROJECT_ROOT / "data" / "PS_20174392719_1491204439457_log.csv"
VECTOR_DB_PATH = PROJECT_ROOT / "vector_db"
OUTPUT_PATH = PROJECT_ROOT / "rag_output"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 64
KNOWLEDGE_CHUNK_SIZE = 700  # approximate words (~900 tokens for this corpus)
KNOWLEDGE_CHUNK_OVERLAP = 100
PAYSIM_CHUNK_SIZE = 100_000
PAYSIM_MAX_NORMAL_CASES = 10_000
PAYSIM_MAX_ACCOUNT_PROFILES = 50_000
CHROMA_BATCH_SIZE = 256
TOP_K = 5
COLLECTION_KNOWLEDGE = "fraud_knowledge"
COLLECTION_PAYSIM = "paysim_cases"

# Retrieval orchestration limits. Chroma distances use cosine distance (lower is closer).
RAG_TOP_K_KNOWLEDGE = 5
RAG_TOP_K_PAYSIM = 5
CASSANDRA_RECENT_TRANSACTION_LIMIT = 20
CASSANDRA_RECENT_ALERT_LIMIT = 10
RAG_MAX_CONTEXT_TRANSACTIONS = 20
RAG_MAX_CONTEXT_ALERTS = 10
RAG_MAX_KNOWLEDGE_CHUNKS = 5
RAG_MAX_PAYSIM_CASES = 5
RAG_CANDIDATE_MULTIPLIER = 3
# None disables distance filtering; set a cosine-distance ceiling to opt in.
RAG_MAX_KNOWLEDGE_DISTANCE = None
RAG_MAX_PAYSIM_DISTANCE = None
# Maximum larger/smaller amount ratio considered a similar PaySim amount range.
RAG_SIMILAR_AMOUNT_FACTOR = 2.0
RAG_KAFKA_CONSUMER_GROUP = "rag-investigation-context"
