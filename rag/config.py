"""Paths and tunable settings for the local RAG vector database."""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "fraud_rag_knowledge_base"
PAYSIM_PATH = PROJECT_ROOT / "data" / "PS_20174392719_1491204439457_log.csv"
VECTOR_DB_PATH = Path(os.getenv("VECTOR_DB_PATH", str(PROJECT_ROOT / "vector_db")))
if not VECTOR_DB_PATH.is_absolute():
    VECTOR_DB_PATH = PROJECT_ROOT / VECTOR_DB_PATH
OUTPUT_PATH = PROJECT_ROOT / "rag_output"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_BATCH_SIZE = 64
KNOWLEDGE_CHUNK_SIZE = 700  # approximate words (~900 tokens for this corpus)
KNOWLEDGE_CHUNK_OVERLAP = 100
PAYSIM_CHUNK_SIZE = 100_000
PAYSIM_MAX_NORMAL_CASES = 10_000
PAYSIM_MAX_ACCOUNT_PROFILES = 50_000
CHROMA_BATCH_SIZE = 256
TOP_K = int(os.getenv("RAG_TOP_K_KNOWLEDGE", "5"))
COLLECTION_KNOWLEDGE = os.getenv("CHROMA_KNOWLEDGE_COLLECTION", "fraud_knowledge")
COLLECTION_PAYSIM = os.getenv("CHROMA_PAYSIM_COLLECTION", "paysim_cases")

# Retrieval orchestration limits. Chroma distances use cosine distance (lower is closer).
RAG_TOP_K_KNOWLEDGE = int(os.getenv("RAG_TOP_K_KNOWLEDGE", "5"))
RAG_TOP_K_PAYSIM = int(os.getenv("RAG_TOP_K_PAYSIM", "5"))
CASSANDRA_RECENT_TRANSACTION_LIMIT = int(os.getenv("CASSANDRA_RECENT_TRANSACTION_LIMIT", "20"))
CASSANDRA_RECENT_ALERT_LIMIT = int(os.getenv("CASSANDRA_RECENT_ALERT_LIMIT", "10"))
RAG_MAX_CONTEXT_TRANSACTIONS = int(os.getenv("RAG_MAX_CONTEXT_TRANSACTIONS", "20"))
RAG_MAX_CONTEXT_ALERTS = int(os.getenv("RAG_MAX_CONTEXT_ALERTS", "10"))
RAG_MAX_KNOWLEDGE_CHUNKS = RAG_TOP_K_KNOWLEDGE
RAG_MAX_PAYSIM_CASES = RAG_TOP_K_PAYSIM
RAG_CANDIDATE_MULTIPLIER = 3
# None disables distance filtering; set a cosine-distance ceiling to opt in.
RAG_MAX_KNOWLEDGE_DISTANCE = None
RAG_MAX_PAYSIM_DISTANCE = None
# Maximum larger/smaller amount ratio considered a similar PaySim amount range.
RAG_SIMILAR_AMOUNT_FACTOR = 2.0
RAG_KAFKA_CONSUMER_GROUP = "rag-investigation-context"
