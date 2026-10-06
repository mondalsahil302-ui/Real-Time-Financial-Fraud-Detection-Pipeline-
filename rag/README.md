# Local fraud RAG vector database

This package builds two persistent ChromaDB collections beside the existing fraud pipeline. It does not replace Cassandra or modify the streaming and model code.

## Why this layer exists

Markdown guidance is divided into heading-aware chunks so a retrieval result contains one coherent topic instead of an entire long document. A local `sentence-transformers/all-MiniLM-L6-v2` model turns chunks and historical case summaries into vectors. ChromaDB stores those vectors and metadata on disk for semantic similarity search without an API key.

`fraud_knowledge` contains Markdown regulatory and investigation guidance. Its metadata preserves authority, version, and status. Documents under historical paths or named as older guidance are marked `status=historical` and `current_authority=false`; the 2024 RBI material is marked current. `paysim_cases` contains synthetic historical examples and profiles. It is reference material, not live customer history.

Raw PaySim rows are not individually embedded as arbitrary CSV strings. Fraud rows become readable case documents, normal transactions are selected by a reproducible hash-based bottom-K sample, and a second chunked scan aggregates activity for accounts linked to fraud. Account summaries are retained for only those accounts, bounding the aggregation state. The CSV is never read into memory as a whole.

## Install and build

From the project root:

```powershell
pip install -r requirements.txt
python -m rag.build_vector_db
```

The knowledge source is `fraud_rag_knowledge_base/` in this checkout. All Markdown files in that directory are chunked and indexed; JSON metadata is used for provenance where it is reflected in Markdown front matter, not embedded as normal knowledge. The PaySim source defaults to `data/PS_20174392719_1491204439457_log.csv`.

The first build downloads the embedding model into the local Hugging Face cache if needed; subsequent builds load it from the local cache. Use `--rebuild` to replace the two RAG collections; normal runs use deterministic IDs, skip unchanged records, and upsert changed or new records. Other options:

```powershell
python -m rag.build_vector_db --knowledge-only
python -m rag.build_vector_db --paysim-only
python -m rag.build_vector_db --max-normal 5000 --paysim-chunk-size 50000
python -m rag.build_vector_db --rebuild
```

The Chroma files are stored under `vector_db/`. Build statistics and actual retrieval examples are written to `rag_output/build_manifest.json` and `rag_output/retrieval_tests.json`.

## Query and inspect

```powershell
python -m rag.query_vector_db "What are early warning signals for fraud?"
python -m rag.query_vector_db "Find historical PaySim fraud cases involving suspicious transfers"
python -m rag.query_vector_db "What is a Red Flagged Account?" --collection fraud_knowledge
python -m rag.query_vector_db "Find suspicious cash-out examples" --collection paysim_cases
python -m rag.inspect_vector_db
```

Query results show distance, ID, source, full metadata, and retrieved text. Metadata makes current RBI guidance distinguishable from historical reference material.

## Later RAG integration

The future context builder can combine a live alert and structured account history from Cassandra with regulatory guidance from `fraud_knowledge` and analogous synthetic examples from `paysim_cases`. Cassandra remains authoritative for live account and transaction history; these collections supply semantic reference context to a later investigation or explanation layer.

## RAG Retrieval Orchestration

The retrieval-only orchestrator accepts the fraud-alert JSON contract already used by `database/fraud_alert_consumer.py` and normalizes its `type`, `nameOrig`, `nameDest`, and balance field names. It then performs three separate bounded reads:

```text
fraud-alerts Kafka -> normalized alert
                         |-> Cassandra: live alert, recent account transactions, previous alerts, prior investigation records
                         |-> Chroma fraud_knowledge: RBI/domain evidence, with current primary sources ranked first
                         |-> Chroma paysim_cases: synthetic historical analogues, ranked by type, amount range, balance behavior, then distance
                         v
                structured investigation context -> rag_output/investigations/<alert_id>.json
```

Cassandra is the source for live structured account context. `fraud_knowledge` supplies regulatory and domain guidance with its original authority, source type, version, and current/historical status. `paysim_cases` supplies historical synthetic references only; PaySim labels do not establish the status of the live alert. Ranking is deterministic and retains Chroma distances. Optional cosine-distance ceilings are configurable in `rag/config.py` and disabled by default. Retrieval errors are recorded per source so one unavailable backend does not prevent context generation from the others.

This phase does not call an LLM. The context separates factual live data, regulatory evidence, historical synthetic evidence, and model outputs. A later LLM can receive this inspectable artifact as context for reasoning and explanation.

Run the retrieval unit tests and offline demo from the project root:

```powershell
python -m pytest tests/test_rag_retrieval.py
python .\tools\test_rag_investigation_context.py
```

The offline demo uses an explicitly marked `source=rag_test` alert and does not publish to Kafka or write to Cassandra. It still attempts read-only Cassandra retrieval and records a Cassandra failure if the service is unavailable. To process a single alert JSON file, run `python -m rag.investigation.process_alert --alert-json path\to\alert.json`. To continuously consume the configured alert topic, run `python -m rag.investigation.process_alert --consume-kafka`.
# Complete investigation path

```text
fraud-alerts Kafka -> investigation consumer -> RAG orchestrator
  -> Cassandra account history + Chroma RBI knowledge + Chroma PaySim
  -> bounded context -> Gemini (gemini-3.5-flash-lite) -> validated report
  -> Cassandra fraud_detection.investigation_results -> Kafka offset commit
```

Gemini is the only LLM for both formal investigations and Ask AI chat. Configure LLM_PROVIDER=gemini, GEMINI_MODEL
(default gemini-3.5-flash-lite), and a server-side GEMINI_API_KEY in .env. Keep the key only in the backend
environment; never add it to frontend/Vite variables or commit it. LLM_FALLBACK_PROVIDER is not supported: a Gemini
failure is surfaced explicitly. Gemini retrieval remains in front of the model: transaction/account questions use
bounded Cassandra history and relevant Chroma evidence, regulatory questions exclude PaySim, and historical comparisons
keep PaySim fraud and normal cases separate. Check provider configuration with http://localhost:8001/api/llm/status;
check Gemini with python .\\tools\\test_llm_connection.py. Check provider
configuration with `http://localhost:8001/api/llm/status`; check Gemini with `python .\\tools\\test_llm_connection.py`.

Run a no-Cassandra local artifact investigation with `python .\\tools\\test_llm_investigation.py`. It reads the
existing synthetic retrieval context and writes a sibling result JSON. The live Kafka service is started with
`python -m rag.investigation.kafka_investigation_consumer`; it consumes `FRAUD_ALERTS_TOPIC` with the dedicated
`KAFKA_INVESTIGATION_CONSUMER_GROUP`, persists a completed, partial, or controlled failed result before committing.
Duplicate alert IDs already present in Cassandra are returned without a second insert. Retrieval artifacts separate
synthetic PaySim fraud and normal examples, preserve source metadata, and are bounded to configured top-K/context limits.
Compare configuration or prompt revisions on a persisted completed fraud alert with
`python .\\tools\\evaluate_llm_providers.py --transaction-id <transaction-id>`. The report is written under
`rag_output/evaluations/`, contains no API key, and labels its relevance/grounding checks as heuristics requiring
manual review.

Troubleshooting: Cassandra failures prevent Kafka commits and are retried; Chroma retrieval failures produce a
partial investigation with missing-source uncertainty; Gemini unavailable, misconfigured, timed out, or returning a
malformed response creates a controlled failed result; Kafka broker/topic errors
are reported by the consumer and do not commit the affected offset.

Suggested local run order:

```powershell
docker start fraud-cassandra
# Set GEMINI_API_KEY in .env, then:
python .\tools\test_llm_connection.py
python .\tools\test_rag_investigation_context.py
python .\tools\test_llm_investigation.py
python .\tools\test_investigation_persistence.py
python -m rag.investigation.kafka_investigation_consumer
```

In another terminal, `python .\tools\test_live_investigation_flow.py` publishes one `source=rag_test` alert with
synthetic account IDs to the configured fraud-alert topic. Cassandra connection/schema tests are
`python -m pytest tests/test_cassandra_connection.py tests/test_cassandra_schema.py -q`; mocked LLM and Kafka tests
run with `python -m pytest tests/test_llm_provider.py tests/test_investigation_schema.py tests/test_investigation_prompt.py tests/test_investigation_service.py tests/test_kafka_investigation_consumer.py -q`.
