"""Compare Ask AI providers on one already-completed Control Center transaction."""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.chat import AssistantUnavailable, _general_context, _intent, _transaction_context, answer_chat
from backend.app.config import sqlite_path
from backend.app.schemas import AssistantChatRequest
from backend.app.storage import Store
from rag.investigation.llm_provider import LLMProviderError, create_llm_provider

QUESTIONS = (
    "Why was this transaction flagged?",
    "What is the strongest risk factor?",
    "What evidence is missing?",
    "Compare this with historical fraud cases.",
    "Compare this with normal historical cases.",
    "What does the RBI evidence say?",
    "Explain the decision path.",
    "What should I clarify in a follow-up review?",
    "What is the customer's occupation?",
    "What device did the customer use?",
    "What is the customer's IP?",
    "What was the anomaly score of the similar historical PaySim case?",
    "Is this definitely fraud because the PaySim case was fraud?",
)
GENERAL_QUESTION = "What general digital-payment early-warning guidance is supported by retrieved sources?"

STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before",
    "case", "does", "evidence", "from", "historical", "how", "into", "this", "that",
    "the", "their", "there", "these", "they", "this", "through", "what", "when",
    "where", "which", "with", "would", "your",
}
ABSENCE_LANGUAGE = ("not present", "not available", "no relevant", "not retrieved", "missing evidence")
UNSUPPORTED_CLAIM_PATTERNS = {
    "occupation": re.compile(r"\b(?:works as|occupation is|is employed as|customer is a)\b", re.I),
    "device": re.compile(r"\b(?:uses an? (?:iphone|android|device)|device (?:is|was))\b", re.I),
    "ip_address": re.compile(r"\b(?:ip(?: address)? is|ip address:?)\s*\d{1,3}(?:\.\d{1,3}){3}\b", re.I),
    "historical_score": re.compile(r"\b(?:paysim|historical case).{0,40}(?:score was|anomaly score)\s*[:=]?\s*\d", re.I),
    "definitive_fraud": re.compile(r"\b(?:definitely|certainly|proves?) fraud\b", re.I),
}


class EvaluationStore:
    """Provide conversation continuity without persisting evaluation chat turns."""

    def __init__(self, store: Store):
        self.store = store
        self.messages: dict[str, list[dict]] = {}

    def transaction(self, transaction_id: str) -> dict | None:
        return self.store.transaction(transaction_id)

    def chat_messages(self, conversation_id: str) -> list[dict] | None:
        return self.messages.get(conversation_id)

    def save_chat_message(self, conversation_id: str, transaction_id: str | None,
                          role: str, content: str) -> None:
        self.messages.setdefault(conversation_id, []).append({
            "conversation_id": conversation_id,
            "transaction_id": transaction_id,
            "role": role,
            "content": content,
        })


def _number_literals(text: str) -> set[str]:
    return {value.lstrip("+") for value in re.findall(r"(?<![\w])[-+]?\d+(?:\.\d+)?(?![\w])", text)}


def _evidence_numbers(evidence: list[dict]) -> set[str]:
    numbers = set()

    def visit(value, key: str = ""):
        if isinstance(value, dict):
            for child_key, child in value.items():
                if not child_key.lower().endswith("_id") and child_key.lower() not in {
                    "transaction_id", "batch_id", "alert_id", "investigation_id", "event_time",
                }:
                    visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            numbers.update(_number_literals(str(value)))
        elif isinstance(value, str):
            numbers.update(_number_literals(value))

    for item in evidence:
        visit(item.get("content"))
    return numbers


def assess(question: str, response: dict, evidence: list[dict]) -> dict:
    answer = response.get("answer", "")
    answer_tokens = set(re.findall(r"[a-z0-9]+", answer.casefold())) - STOP_WORDS
    question_tokens = set(re.findall(r"[a-z0-9]+", question.casefold())) - STOP_WORDS
    relevance = len(answer_tokens & question_tokens) / max(1, len(question_tokens))

    answer_numbers = _number_literals(answer)
    evidence_numbers = _evidence_numbers(evidence)
    numeric_grounding = (
        len(answer_numbers & evidence_numbers) / len(answer_numbers)
        if answer_numbers else 1.0
    )

    cited = response.get("evidence", [])
    attributed = [
        item for item in cited
        if item.get("source_id") and item.get("source_type")
    ]
    source_attribution = len(attributed) / max(1, len(cited))

    missing = response.get("missing_evidence", [])
    missing_text = answer.casefold()
    missing_handling = (
        None if not missing
        else float(any(phrase in missing_text for phrase in ABSENCE_LANGUAGE))
    )

    unsupported = [
        label for label, pattern in UNSUPPORTED_CLAIM_PATTERNS.items()
        if pattern.search(answer)
    ]
    return {
        "relevance_keyword_overlap": round(relevance, 4),
        "numeric_grounding_fraction": round(numeric_grounding, 4),
        "source_attribution_completeness": round(source_attribution, 4),
        "missing_evidence_acknowledged": missing_handling,
        "unsupported_claim_flags": unsupported,
        "assessment_note": "Heuristic checks only; review the answer and evidence manually.",
    }


def evaluate(transaction_id: str) -> Path:
    store = EvaluationStore(Store(sqlite_path()))
    transaction = store.transaction(transaction_id)
    if transaction is None:
        raise ValueError("Transaction ID was not found in the Control Center store.")
    if str(transaction.get("final_decision", "")).upper() != "FRAUD_ALERT":
        raise ValueError("Choose a persisted FRAUD_ALERT transaction.")
    if str(transaction.get("investigation_status", "")).upper() != "COMPLETED":
        raise ValueError("Choose a fraud alert with a COMPLETED investigation.")

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "transaction_kind": "completed_fraud_alert",
        "evaluations": [],
        "api_keys_stored": False,
    }

    for provider_name in ("gemini",):
        conversation_id = str(uuid.uuid4())
        for question in QUESTIONS:
            evidence_cache = {}

            def retrieve(current_transaction, request):
                if _intent(request.question) == "regulatory":
                    result = _general_context(request.question)
                else:
                    result = _transaction_context(
                        current_transaction,
                        question=request.question,
                        include_cassandra=True,
                        include_fraud_knowledge=True,
                        include_paysim_cases=True,
                    )
                evidence_cache[request.question] = result
                return result

            try:
                provider = create_llm_provider(provider_name)
                started = time.perf_counter()
                response = answer_chat(
                    AssistantChatRequest(
                        question=question,
                        transaction_id=transaction_id,
                        conversation_id=conversation_id if store.chat_messages(conversation_id) else None,
                    ),
                    store,
                    provider=provider,
                    retrieval=retrieve,
                )
                conversation_id = response["conversation_id"]
                raw_alert = transaction.get("payload") or {}
                evidence, _ = evidence_cache[question]
                elapsed = time.perf_counter() - started
                report["evaluations"].append({
                    "provider": response["llm_provider"],
                    "model": response["llm_model"],
                    "question": question,
                    "answer": response["answer"],
                    "evidence": response["evidence"],
                    "missing_evidence": response["missing_evidence"],
                    "latency_seconds": elapsed,
                    "metrics": assess(question, response, evidence),
                    "transaction_type": raw_alert.get("type") or raw_alert.get("transaction_type"),
                    "status": "success",
                })
            except (AssistantUnavailable, LLMProviderError, ValueError) as exc:
                report["evaluations"].append({
                    "provider": provider_name,
                    "model": "",
                    "question": question,
                    "status": "failed",
                    "error": str(exc),
                })

        try:
            provider = create_llm_provider(provider_name)
            started = time.perf_counter()
            response = answer_chat(
                AssistantChatRequest(question=GENERAL_QUESTION),
                store,
                provider=provider,
            )
            report["evaluations"].append({
                "provider": response["llm_provider"],
                "model": response["llm_model"],
                "question": GENERAL_QUESTION,
                "answer": response["answer"],
                "evidence": response["evidence"],
                "missing_evidence": response["missing_evidence"],
                "latency_seconds": time.perf_counter() - started,
                "metrics": assess(GENERAL_QUESTION, response, response["evidence"]),
                "status": "success",
            })
        except (AssistantUnavailable, LLMProviderError, ValueError) as exc:
            report["evaluations"].append({
                "provider": provider_name,
                "model": "",
                "question": GENERAL_QUESTION,
                "status": "failed",
                "error": str(exc),
            })

    output_dir = Path(__file__).resolve().parents[1] / "rag_output" / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"provider_evaluation_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction-id", required=True)
    args = parser.parse_args()
    try:
        output_path = evaluate(args.transaction_id)
    except (AssistantUnavailable, ValueError) as exc:
        parser.error(str(exc))
    print(f"Provider evaluation saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
