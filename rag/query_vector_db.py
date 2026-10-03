"""Query the local fraud RAG Chroma collections."""
import argparse
import json
import sys

import chromadb

from rag import config
from rag.embedder import LocalEmbedder


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural-language query")
    parser.add_argument("--collection", choices=(config.COLLECTION_KNOWLEDGE, config.COLLECTION_PAYSIM))
    parser.add_argument("--top-k", type=int, default=config.TOP_K)
    args = parser.parse_args()
    client = chromadb.PersistentClient(path=str(config.VECTOR_DB_PATH))
    embedder = LocalEmbedder(config.EMBEDDING_MODEL)
    names = [args.collection] if args.collection else [config.COLLECTION_KNOWLEDGE, config.COLLECTION_PAYSIM]
    for name in names:
        try: collection = client.get_collection(name)
        except Exception as exc: raise RuntimeError(f"Collection {name!r} is unavailable; build the database first") from exc
        if not collection.count():
            print(f"{name}: empty collection")
            continue
        result = collection.query(query_embeddings=embedder.encode([args.query]), n_results=min(args.top_k, collection.count()))
        print(f"\n## {name}")
        for idx, doc_id in enumerate(result["ids"][0]):
            print(f"\n[{idx + 1}] distance={result['distances'][0][idx]:.6f} id={doc_id}")
            print(f"source={result['metadatas'][0][idx].get('relative_path', result['metadatas'][0][idx].get('dataset', 'unknown'))}")
            print("metadata=" + json.dumps(result["metadatas"][0][idx], ensure_ascii=False, sort_keys=True))
            print("text=" + result["documents"][0][idx])


if __name__ == "__main__": main()
