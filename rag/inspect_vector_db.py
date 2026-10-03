"""Inspect collection sizes and a sample of stored vector documents."""
import chromadb

from rag import config


def main():
    client = chromadb.PersistentClient(path=str(config.VECTOR_DB_PATH))
    for name in (config.COLLECTION_KNOWLEDGE, config.COLLECTION_PAYSIM):
        try: collection = client.get_collection(name)
        except Exception:
            print(f"{name}\ncount: unavailable")
            continue
        print(f"{name}\ncount: {collection.count()}")
        if collection.count():
            sample = collection.get(limit=min(3, collection.count()), include=["metadatas", "documents", "embeddings"])
            dimensions = len(sample["embeddings"][0]) if sample.get("embeddings") is not None and len(sample["embeddings"]) else "unknown"
            print(f"embedding dimension: {dimensions}")
            for doc_id, metadata, document in zip(sample["ids"], sample["metadatas"], sample["documents"]):
                print(f"sample id: {doc_id}\nmetadata: {metadata}\ndocument: {document[:500]}\n")


if __name__ == "__main__": main()
