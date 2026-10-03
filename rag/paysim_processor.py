"""Chunked PaySim to retrieval-document conversion."""
from __future__ import annotations

import hashlib
import heapq
import json
import logging
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

import pandas as pd
from tqdm import tqdm

LOGGER = logging.getLogger(__name__)
ROW_FIELDS = ("step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud")


def paysim_id(kind: str, key: str) -> str:
    return f"paysim_{kind}_{hashlib.sha256(str(key).encode('utf-8')).hexdigest()}"


def _present(row: dict, key: str) -> bool:
    return key in row and pd.notna(row[key]) and row[key] != ""


def _decimal(value) -> Decimal | None:
    """Parse a source value exactly enough for base-10 balance comparisons."""
    try:
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def row_document(row: dict, label: str) -> tuple[str, dict]:
    available = [key for key in ROW_FIELDS if _present(row, key)]
    values = {key: row[key] for key in available}
    def val(key):
        return str(values[key])
    lines = [f"Historical PaySim {'Fraud' if label == 'fraud' else 'Normal'} Case"]
    names = {"type": "Transaction type", "step": "Step", "amount": "Amount", "nameOrig": "Origin account", "oldbalanceOrg": "Origin balance before", "newbalanceOrig": "Origin balance after", "nameDest": "Destination account", "oldbalanceDest": "Destination balance before", "newbalanceDest": "Destination balance after", "isFraud": "Fraud label", "isFlaggedFraud": "Flagged by source dataset"}
    for key in available:
        fraud_value = key == "isFraud" and _decimal(values[key]) == Decimal(1)
        lines.append(f"{names.get(key, key)}: {'FRAUD' if fraud_value else 'NORMAL' if key == 'isFraud' else val(key)}")
    derived: dict[str, object] = {}
    old_origin = _decimal(values.get("oldbalanceOrg"))
    new_origin = _decimal(values.get("newbalanceOrig"))
    if old_origin is not None and new_origin is not None:
        depleted = old_origin > 0 and new_origin == 0
        unchanged = old_origin == new_origin
        change = new_origin - old_origin
        derived.update({
            "origin_balance_depleted": depleted,
            "origin_balance_unchanged": unchanged,
            "balance_change_amount": format(change, "f"),
        })
        if depleted:
            lines.append("Observed transactional characteristics: Origin account balance was depleted to zero after the transaction.")
        elif old_origin == 0 and new_origin == 0:
            lines.append("Observed transactional characteristics: Origin account had zero balance before and after the transaction.")
        elif unchanged:
            lines.append(f"Observed transactional characteristics: Origin account balance was unchanged at {val('oldbalanceOrg')} before and after the transaction.")
        elif change < 0:
            lines.append(f"Observed transactional characteristics: Origin account balance decreased from {val('oldbalanceOrg')} to {val('newbalanceOrig')}.")
        else:
            lines.append(f"Observed transactional characteristics: Origin account balance increased from {val('oldbalanceOrg')} to {val('newbalanceOrig')}.")

    old_destination = _decimal(values.get("oldbalanceDest"))
    new_destination = _decimal(values.get("newbalanceDest"))
    if old_destination is not None and new_destination is not None:
        destination_increased = new_destination > old_destination
        destination_unchanged = new_destination == old_destination
        derived.update({
            "destination_balance_increased": destination_increased,
            "destination_balance_unchanged": destination_unchanged,
        })
        if destination_increased:
            lines.append(f"Observed transactional characteristics: Destination account balance increased from {val('oldbalanceDest')} to {val('newbalanceDest')}.")
        elif destination_unchanged:
            lines.append(f"Observed transactional characteristics: Destination account balance was unchanged at {val('oldbalanceDest')}.")
        else:
            lines.append(f"Observed transactional characteristics: Destination account balance decreased from {val('oldbalanceDest')} to {val('newbalanceDest')}.")
    meta = {
        "source_type": "paysim", "document_type": "fraud_case" if label == "fraud" else "normal_case",
        "dataset": "PaySim", "label": label,
        "transaction_type": str(values.get("type", "unknown")),
        "source_row_id": str(row.get("source_row_id", "")),
    }
    for key in ("isFraud", "step", "amount"):
        if key in values:
            meta[key] = val(key)
    meta.update(derived)
    return "\n".join(lines), meta


def iter_case_documents(csv_path: Path, chunk_size: int, max_normal: int, max_profiles: int = 50_000, progress: bool = True) -> tuple[Iterator[tuple[str, str, dict]], dict]:
    """Scan twice: harvest fraud and deterministic bottom-K normals, then summarize fraud accounts."""
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"PaySim CSV not found: {csv_path}")
    selected_normal: list[tuple[str, dict]] = []  # max heap encoded as negative digest
    fraud_rows: list[dict] = []  # PaySim fraud rows are sparse, this list remains small
    fraud_accounts: set[str] = set()
    rows_processed = 0
    reader = pd.read_csv(csv_path, chunksize=chunk_size, on_bad_lines="warn", dtype=str)
    for chunk in tqdm(reader, desc="Scanning PaySim", disable=not progress):
        chunk = chunk.where(pd.notna(chunk), None)
        for raw in chunk.to_dict(orient="records"):
            row = dict(raw)
            row["source_row_id"] = str(rows_processed)
            rows_processed += 1
            if int(float(row.get("isFraud") or 0)) == 1:
                fraud_rows.append(row)
                for key in ("nameOrig", "nameDest"):
                    if row.get(key): fraud_accounts.add(str(row[key]))
            else:
                # Bottom-K SHA-256 keeps a deterministic, order-independent sample.
                digest = hashlib.sha256(f"{row.get('step')}|{row.get('type')}|{row.get('nameOrig')}|{row.get('nameDest')}|{row.get('amount')}|{rows_processed}".encode()).hexdigest()
                score = int(digest, 16)
                if max_normal > 0 and len(selected_normal) < max_normal:
                    heapq.heappush(selected_normal, (-score, row))
                elif max_normal > 0 and score < -selected_normal[0][0]:
                    heapq.heapreplace(selected_normal, (-score, row))
    docs: list[tuple[str, str, dict]] = []
    for row in fraud_rows:
        text, meta = row_document(row, "fraud")
        docs.append((paysim_id("fraud", meta["source_row_id"]), text, meta))
    for _, row in sorted(selected_normal, key=lambda pair: -pair[0]):
        text, meta = row_document(row, "normal")
        docs.append((paysim_id("normal", meta["source_row_id"]), text, meta))

    # Second pass stores aggregates only for fraud-linked accounts, not all accounts.
    summaries = defaultdict(lambda: {"transactions": 0, "amount": 0.0, "fraud_transactions": 0, "types": defaultdict(int), "first_step": None, "last_step": None})
    if fraud_accounts:
        for chunk in tqdm(pd.read_csv(csv_path, chunksize=chunk_size, on_bad_lines="warn", dtype=str), desc="Summarizing fraud-linked accounts", disable=not progress):
            for row in chunk.to_dict(orient="records"):
                step = int(row["step"])
                fraud = int(row["isFraud"])
                for role, field in (("origin", "nameOrig"), ("destination", "nameDest")):
                    account = str(row[field])
                    if account not in fraud_accounts:
                        continue
                    agg = summaries[account]
                    agg["transactions"] += 1
                    agg["amount"] += float(row["amount"])
                    agg["fraud_transactions"] += fraud
                    agg["types"][str(row["type"])] += 1
                    agg["first_step"] = step if agg["first_step"] is None else min(step, agg["first_step"])
                    agg["last_step"] = step if agg["last_step"] is None else max(step, agg["last_step"])
                    agg["role"] = role
    profiles = 0
    for account in sorted(summaries)[:max_profiles]:
        agg = summaries[account]
        text = (f"PaySim account behavior profile\nAccount: {account}\nObserved role: {agg.get('role', 'origin or destination')}\n"
                f"Transactions: {agg['transactions']}\nFraud-labeled transactions: {agg['fraud_transactions']}\n"
                f"Total observed amount: {agg['amount']:.2f}\nTransaction types: {json.dumps(dict(sorted(agg['types'].items())), sort_keys=True)}\n"
                f"Observed step range: {agg['first_step']} to {agg['last_step']}")
        meta = {"source_type": "paysim", "document_type": "account_behavior_profile", "dataset": "PaySim", "account_id": account,
                "transaction_count": int(agg["transactions"]), "fraud_transaction_count": int(agg["fraud_transactions"]),
                "total_amount": float(agg["amount"]), "first_step": int(agg["first_step"]), "last_step": int(agg["last_step"])}
        docs.append((paysim_id("account", account), text, meta))
        profiles += 1
    counts = {"rows_processed": rows_processed, "fraud_documents": len(fraud_rows), "normal_documents": len(selected_normal), "account_profiles": profiles}
    return iter(docs), counts
