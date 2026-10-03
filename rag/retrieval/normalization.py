"""Normalize source fraud-alert fields into a stable retrieval contract."""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from typing import Mapping

FIELD_ALIASES = {
    "type": "transaction_type",
    "nameOrig": "name_orig",
    "nameDest": "name_dest",
    "oldbalanceOrg": "old_balance_orig",
    "newbalanceOrig": "new_balance_orig",
    "oldbalanceDest": "old_balance_dest",
    "newbalanceDest": "new_balance_dest",
}


def normalize_alert(alert: Mapping) -> dict:
    """Accept Kafka JSON, Cassandra-style columns, or already-normalized alerts."""
    if not isinstance(alert, Mapping):
        raise TypeError("alert must be a mapping")
    normalized = dict(alert)
    for source, target in FIELD_ALIASES.items():
        if target not in normalized and source in alert:
            normalized[target] = alert[source]
        normalized.pop(source, None)
    if "transaction_id" in normalized and normalized["transaction_id"] is not None:
        normalized["transaction_id"] = str(normalized["transaction_id"])
    if normalized.get("alert_id") not in (None, ""):
        normalized["alert_id"] = str(normalized["alert_id"])
    elif normalized.get("transaction_id"):
        normalized["alert_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fraud-alert:{normalized['transaction_id']}"))
    else:
        stable = hashlib.sha256(repr(sorted((str(k), str(v)) for k, v in normalized.items())).encode()).hexdigest()
        normalized["alert_id"] = f"alert_{stable}"
    event_time = normalized.get("event_time")
    if isinstance(event_time, datetime):
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        normalized["event_time"] = event_time.astimezone(timezone.utc).isoformat()
    elif event_time is not None:
        normalized["event_time"] = str(event_time)
    if normalized.get("event_date") is None and normalized.get("event_time"):
        try:
            normalized["event_date"] = datetime.fromisoformat(normalized["event_time"].replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    elif isinstance(normalized.get("event_date"), date):
        normalized["event_date"] = normalized["event_date"].isoformat()
    if normalized.get("event_hour") is None and normalized.get("event_time"):
        try:
            normalized["event_hour"] = datetime.fromisoformat(normalized["event_time"].replace("Z", "+00:00")).hour
        except ValueError:
            pass
    return normalized
