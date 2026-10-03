"""Transparent deterministic ordering and evidence de-duplication."""
from __future__ import annotations

import math

from rag import config


def _distance(item: dict) -> float:
    try:
        value = float(item.get("distance", math.inf))
        return value if math.isfinite(value) else math.inf
    except (TypeError, ValueError):
        return math.inf


def deduplicate(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    seen: set[str] = set()
    output = []
    for item in items:
        value = next((item.get(key) for key in keys if item.get(key) not in (None, "")), None)
        identity = str(value) if value is not None else str(item.get("document_id", item.get("id", repr(sorted(item.items())))))
        if identity not in seen:
            seen.add(identity)
            output.append(item)
    return output


def _knowledge_priority(metadata: dict) -> int:
    status = str(metadata.get("status", "")).lower()
    source_type = str(metadata.get("source_type", "")).lower()
    authority = str(metadata.get("authority", "")).lower()
    if status == "current" and metadata.get("current_authority") is True and authority == "rbi" and source_type == "primary_regulatory":
        return 0
    if status == "current" and metadata.get("current_authority") is True:
        return 1
    if source_type == "secondary_analysis":
        return 2
    if status == "historical" or source_type == "historical_reference":
        return 3
    return 2


def rank_knowledge(items: list[dict], top_k: int | None = None) -> list[dict]:
    unique = deduplicate(items, ("document_id",))
    for item in unique:
        item["ranking_reason"] = {
            "current_rbi_primary": _knowledge_priority(item.get("metadata", {})) == 0,
            "metadata_priority": _knowledge_priority(item.get("metadata", {})),
            "vector_distance": item.get("distance"),
        }
    unique.sort(key=lambda item: (_knowledge_priority(item.get("metadata", {})), _distance(item), str(item.get("document_id", ""))))
    return unique[:top_k] if top_k is not None else unique


def _num(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def rank_paysim(items: list[dict], alert: dict, top_k: int | None = None) -> list[dict]:
    unique = deduplicate(items, ("source_row_id",))
    alert_type = str(alert.get("transaction_type", "")).upper()
    alert_amount = _num(alert.get("amount"))
    old = _num(alert.get("old_balance_orig"))
    new = _num(alert.get("new_balance_orig"))
    alert_origin_delta = new - old if old is not None and new is not None else None
    alert_origin_depleted = old > 0 and new == 0 if old is not None and new is not None else None
    alert_origin_unchanged = old == new if old is not None and new is not None else None
    old_dest = _num(alert.get("old_balance_dest"))
    new_dest = _num(alert.get("new_balance_dest"))
    alert_dest_increased = new_dest > old_dest if old_dest is not None and new_dest is not None else None
    alert_dest_unchanged = new_dest == old_dest if old_dest is not None and new_dest is not None else None
    for item in unique:
        metadata = item.get("metadata", {})
        same_type = bool(alert_type) and str(metadata.get("transaction_type", "")).upper() == alert_type
        amount = _num(metadata.get("amount"))
        amount_similar = False
        amount_ratio = math.inf
        if alert_amount is not None and amount is not None:
            amount_ratio = max(alert_amount, amount) / max(min(alert_amount, amount), 1e-12) if max(alert_amount, amount) > 0 else 1.0
            amount_similar = amount_ratio <= config.RAG_SIMILAR_AMOUNT_FACTOR
        comparisons = []
        for case_key, alert_value in (("origin_balance_depleted", alert_origin_depleted),
                                      ("origin_balance_unchanged", alert_origin_unchanged),
                                      ("destination_balance_increased", alert_dest_increased),
                                      ("destination_balance_unchanged", alert_dest_unchanged)):
            case_value = metadata.get(case_key)
            if case_value is not None and alert_value is not None:
                comparisons.append(bool(case_value) == alert_value)
        case_delta = _num(metadata.get("balance_change_amount"))
        if case_delta is not None and alert_origin_delta is not None:
            comparisons.append((case_delta > 0) - (case_delta < 0) == (alert_origin_delta > 0) - (alert_origin_delta < 0))
        balance_score = sum(comparisons) / len(comparisons) if comparisons else None
        item["ranking_reason"] = {"same_transaction_type": same_type, "similar_amount_range": amount_similar,
                                  "amount_ratio": amount_ratio if math.isfinite(amount_ratio) else None,
                                  "balance_behavior_match_score": balance_score,
                                  "balance_behavior_comparisons": len(comparisons),
                                  "vector_distance": item.get("distance")}
    unique.sort(key=lambda item: (-int(item["ranking_reason"]["same_transaction_type"]),
                                  -int(item["ranking_reason"]["similar_amount_range"]),
                                  -(item["ranking_reason"]["balance_behavior_match_score"] or 0.0),
                                  _distance(item), str(item.get("source_row_id", ""))))
    return unique[:top_k] if top_k is not None else unique


def rank_recent(items: list[dict], key_fields: tuple[str, ...], limit: int | None = None) -> list[dict]:
    unique = deduplicate(items, key_fields)
    unique.sort(key=lambda item: str(item.get("event_time", item.get("generated_at", ""))), reverse=True)
    return unique[:limit] if limit is not None else unique
