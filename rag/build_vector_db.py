"""Build or update the two persistent Chroma collections."""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from tqdm import tqdm

from rag import config
from rag.chunker import chunk_markdown, deterministic_id, knowledge_metadata
from rag.embedder import LocalEmbedder
from rag.paysim_processor import iter_case_documents

LOGGER = logging.getLogger("rag.build")


def _add_batch(collection, embedder, docs, batch_size):
    for start in tqdm(range(0, len(docs), batch_size), desc=f"Indexing {collection.name}"):
        batch = docs[start:start + batch_size]
        try:
            existing = collection.get(ids=[x[0] for x in batch], include=["documents", "metadatas"])
            current = {doc_id: (document, metadata) for doc_id, document, metadata in zip(existing["ids"], existing["documents"], existing["metadatas"])}
            changed = [item for item in batch if current.get(item[0]) != (item[1], item[2])]
            if not changed:
                continue
            vectors = embedder.encode([x[1] for x in changed], config.EMBEDDING_BATCH_SIZE)
            collection.upsert(ids=[x[0] for x in changed], documents=[x[1] for x in changed], metadatas=[x[2] for x in changed], embeddings=vectors)
        except Exception:
            LOGGER.exception("Failed to index %s batch beginning at %d", collection.name, start)
            raise


def _prune_stale_managed_documents(collection, expected_ids: set[str], source_type: str) -> None:
    """Remove obsolete records from this source while preserving unrelated records."""
    stale = []
    offset = 0
    while True:
        page = collection.get(limit=1000, offset=offset, include=["metadatas"])
        page_size = len(page["ids"])
        stale.extend(doc_id for doc_id, metadata in zip(page["ids"], page["metadatas"] or [])
                     if metadata and metadata.get("source_type") == source_type and doc_id not in expected_ids)
        offset += page_size
        if page_size < 1000:
            break
    for start in range(0, len(stale), config.CHROMA_BATCH_SIZE):
        collection.delete(ids=stale[start:start + config.CHROMA_BATCH_SIZE])


def build(args: argparse.Namespace) -> dict:
    if not args.paysim_only and not config.KNOWLEDGE_BASE_PATH.is_dir():
        raise FileNotFoundError(f"Knowledge base directory not found: {config.KNOWLEDGE_BASE_PATH}")
    if not args.knowledge_only and not config.PAYSIM_PATH.is_file():
        raise FileNotFoundError(f"PaySim CSV not found: {config.PAYSIM_PATH}")
    try:
        client = chromadb.PersistentClient(path=str(config.VECTOR_DB_PATH))
        if args.rebuild:
            for name in (config.COLLECTION_KNOWLEDGE, config.COLLECTION_PAYSIM):
                try: client.delete_collection(name)
                except Exception as exc:
                    if "does not exist" not in str(exc).lower():
                        raise
        knowledge = client.get_or_create_collection(config.COLLECTION_KNOWLEDGE, metadata={"hnsw:space": "cosine"})
        paysim = client.get_or_create_collection(config.COLLECTION_PAYSIM, metadata={"hnsw:space": "cosine"})
    except Exception as exc:
        raise RuntimeError(f"Could not initialize persistent Chroma at {config.VECTOR_DB_PATH}: {exc}") from exc

    kb_docs = []
    if not args.paysim_only:
        files = sorted(config.KNOWLEDGE_BASE_PATH.rglob("*.md"))
        for path in files:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(config.KNOWLEDGE_BASE_PATH).as_posix()
            for index, text in enumerate(chunk_markdown(content, config.KNOWLEDGE_CHUNK_SIZE, config.KNOWLEDGE_CHUNK_OVERLAP)):
                kb_docs.append((deterministic_id(rel, index, text), text, knowledge_metadata(path, config.KNOWLEDGE_BASE_PATH, index, content)))
        if not files:
            raise ValueError(f"No Markdown documents found under {config.KNOWLEDGE_BASE_PATH}")

    paysim_docs, counts = iter_case_documents(config.PAYSIM_PATH, args.paysim_chunk_size or config.PAYSIM_CHUNK_SIZE,
                                                args.max_normal if args.max_normal is not None else config.PAYSIM_MAX_NORMAL_CASES,
                                                config.PAYSIM_MAX_ACCOUNT_PROFILES,
                                                progress=True) if not args.knowledge_only else (iter(()), {})
    paysim_docs = list(paysim_docs)
    embedder = LocalEmbedder(config.EMBEDDING_MODEL)
    chunk_output = config.OUTPUT_PATH / "chunks"
    paysim_output = config.OUTPUT_PATH / "paysim_documents"
    chunk_output.mkdir(parents=True, exist_ok=True)
    paysim_output.mkdir(parents=True, exist_ok=True)
    if kb_docs:
        with (chunk_output / "knowledge_chunks.jsonl").open("w", encoding="utf-8") as stream:
            for doc_id, text, metadata in kb_docs:
                stream.write(json.dumps({"id": doc_id, "text": text, "metadata": metadata}, ensure_ascii=False) + "\n")
    if paysim_docs:
        with (paysim_output / "paysim_documents.jsonl").open("w", encoding="utf-8") as stream:
            for doc_id, text, metadata in paysim_docs:
                stream.write(json.dumps({"id": doc_id, "text": text, "metadata": metadata}, ensure_ascii=False) + "\n")
    if kb_docs: _add_batch(knowledge, embedder, kb_docs, config.CHROMA_BATCH_SIZE)
    if paysim_docs: _add_batch(paysim, embedder, paysim_docs, config.CHROMA_BATCH_SIZE)
    if not args.paysim_only:
        _prune_stale_managed_documents(knowledge, {item[0] for item in kb_docs}, "regulatory_knowledge")
        _prune_stale_managed_documents(knowledge, {item[0] for item in kb_docs}, "historical_reference")
    if not args.knowledge_only:
        _prune_stale_managed_documents(paysim, {item[0] for item in paysim_docs}, "paysim")

    retrieval_tests = []
    queries = [(config.COLLECTION_KNOWLEDGE, "What are early warning signals for unusual transactions?"),
               (config.COLLECTION_KNOWLEDGE, "What is a Red Flagged Account?"),
               (config.COLLECTION_KNOWLEDGE, "What are the current RBI fraud investigation requirements?"),
               (config.COLLECTION_KNOWLEDGE, "What fraud classification categories are relevant to digital payment fraud?"),
               (config.COLLECTION_PAYSIM, "Find historical PaySim fraud cases involving transfers and balance depletion."),
               (config.COLLECTION_PAYSIM, "Find historical PaySim cases similar to a suspicious cash-out transaction.")]
    for collection_name, query in queries:
        if (args.paysim_only and collection_name == config.COLLECTION_KNOWLEDGE) or (args.knowledge_only and collection_name == config.COLLECTION_PAYSIM):
            continue
        collection = knowledge if collection_name == config.COLLECTION_KNOWLEDGE else paysim
        result = collection.query(query_embeddings=embedder.encode([query]), n_results=min(config.TOP_K, max(1, collection.count())))
        retrieval_tests.append({"query": query, "collection": collection_name, "returned_ids": result["ids"][0],
                                "returned_metadata": result["metadatas"][0], "distances": result["distances"][0],
                                "retrieved_text": result["documents"][0]})
    config.OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT_PATH / "retrieval_tests.json").write_text(json.dumps(retrieval_tests, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {"build_timestamp": datetime.now(timezone.utc).isoformat(), "embedding_model": config.EMBEDDING_MODEL,
                "embedding_dimension": embedder.dimension, "knowledge_files_discovered": len({p.relative_to(config.KNOWLEDGE_BASE_PATH).as_posix() for p in config.KNOWLEDGE_BASE_PATH.rglob("*.md")}) if not args.paysim_only else 0,
                "knowledge_chunks_created": len(kb_docs), "knowledge_vectors_indexed": knowledge.count(),
                "paysim_rows_processed": counts.get("rows_processed", 0), "paysim_fraud_documents": counts.get("fraud_documents", 0),
                "paysim_normal_documents": counts.get("normal_documents", 0), "paysim_account_profiles": counts.get("account_profiles", 0),
                "knowledge_collection_count": knowledge.count(), "paysim_collection_count": paysim.count(),
                "source_paths": {"knowledge_base": str(config.KNOWLEDGE_BASE_PATH), "paysim": str(config.PAYSIM_PATH)},
                "configuration": {"paysim_chunk_size": args.paysim_chunk_size or config.PAYSIM_CHUNK_SIZE,
                                  "paysim_max_normal_cases": args.max_normal if args.max_normal is not None else config.PAYSIM_MAX_NORMAL_CASES,
                                  "paysim_max_account_profiles": config.PAYSIM_MAX_ACCOUNT_PROFILES,
                                  "knowledge_chunk_size": config.KNOWLEDGE_CHUNK_SIZE, "knowledge_chunk_overlap": config.KNOWLEDGE_CHUNK_OVERLAP,
                                  "chroma_batch_size": config.CHROMA_BATCH_SIZE}}
    (config.OUTPUT_PATH / "build_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="delete and recreate the two RAG collections")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--knowledge-only", action="store_true")
    group.add_argument("--paysim-only", action="store_true")
    parser.add_argument("--paysim-chunk-size", type=int)
    parser.add_argument("--max-normal", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(build(args), indent=2))


if __name__ == "__main__": main()
