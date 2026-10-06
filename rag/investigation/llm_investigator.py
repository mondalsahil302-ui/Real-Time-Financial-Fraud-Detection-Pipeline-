"""LLM response parsing, source grounding, and standalone artifact command."""
from __future__ import annotations

import argparse
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rag.investigation.investigation_prompt import build_messages
from rag.investigation.investigation_schema import InvestigationSchemaError, alert_assessment, failure_result, validate_llm_payload, validate_result
from rag.investigation.llm_provider import LLMProvider, LLMProviderError, create_llm_provider
from rag.metrics import DURATION, count

LOGGER = logging.getLogger(__name__)
UNSAFE_CLAIM = re.compile(r"(?:paysim|similarity|similar case|xgboost probability|model probability|model output).{0,100}(?:proves?|confirms?|establishes?|demonstrates?).{0,60}fraud|(?:fraud).{0,60}(?:proven|confirmed|established).{0,60}(?:paysim|similarity|probability|model)", re.IGNORECASE)
MODEL_FIELDS = ("anomaly_score", "xgboost_probability", "risk_level", "final_prediction", "decision_path", "final_decision_path")
UNSUPPORTED_BALANCE_ATTRIBUTION = re.compile(r"(?:RBI|Reserve Bank of India).{0,180}(?:balance|origin|destination|decrease|increase).{0,100}(?:suspicious|fraud|indicator|pattern)|(?:balance|origin|destination).{0,100}(?:RBI|Reserve Bank of India).{0,100}(?:prescribed|defines?|says|states|indicator)", re.I)


def _guard_claim(text: str, summary: bool = False) -> str:
    text = re.sub(r"no previous alerts exist", "no previous alerts were retrieved", text, flags=re.I)
    text = re.sub(r"no previous investigations exist", "no previous investigations were retrieved", text, flags=re.I)
    text = re.sub(r"the account has no history", "no relevant account history was retrieved from Cassandra", text, flags=re.I)
    text = re.sub(r"no account history exists", "no relevant account history was retrieved from Cassandra", text, flags=re.I)
    if UNSAFE_CLAIM.search(text):
        if summary:
            return "The available model signals and synthetic historical similarities are contextual only. They do not establish fraud; review the live evidence and resolve the listed uncertainties."
        return "Claim withheld: model output and synthetic PaySim similarity are not proof. Validate against source evidence."
    return text


def _guard_customer_claim(text: str, context: dict) -> str:
    live_sources = json.dumps({"alert": context.get("alert", {}), "live_account_context": context.get("live_account_context", {})}, ensure_ascii=False).lower()
    unsupported_terms = ("occupation", "located in", "location", "city", "kyc status", "kyc verified", "ip address", "device id",
                         "customer intent", "transaction purpose", "beneficiary relationship", "law enforcement confirmed")
    if any(term in text.lower() and term not in live_sources for term in unsupported_terms):
        return "Claim withheld: no supporting customer/account detail was retrieved."
    return text


def _guard_historical_model_leak(text: str, context: dict) -> str:
    historical = re.search(r"paysim|historical case|historical transaction", text, re.I)
    model_value = re.search(r"anomaly[_ ]score|xgboost[_ ]probability|risk[_ ]level|final[_ ]prediction|decision[_ ]path", text, re.I)
    if historical and model_value:
        phrase = model_value.group(0).lower().replace(" ", "_")
        keys = {"decision_path": ("decision_path", "final_decision_path"), "risk_level": ("risk_level",),
            "final_prediction": ("final_prediction",), "anomaly_score": ("anomaly_score",), "xgboost_probability": ("xgboost_probability",)}.get(phrase, (phrase,))
        explicit = any(any(key in case or key in case.get("metadata", {}) for key in keys) for case in _known_paysim_cases(context))
        if not explicit:
            return "Claim withheld: current alert model outputs cannot be attributed to historical PaySim cases."
    return text


def _safe_regulatory_claim(text: str, context: dict) -> str:
    if not UNSUPPORTED_BALANCE_ATTRIBUTION.search(text):
        return _guard_claim(text)
    # The document must itself mention the claimed balance concepts before an
    # RBI attribution can survive normalization.
    docs = " ".join(str(x.get("text", "")) for x in context.get("regulatory_context", []))
    concepts = re.search(r"balance|origin|destination", docs, re.I) and re.search(r"balance|origin|destination", text, re.I)
    if concepts:
        return _guard_claim(text)
    return "Regulatory fact: the retrieved RBI text covers EWS/RFA and transaction monitoring. Investigation inference: the observed balance movements may be reviewed, but the retrieved text does not define this exact pattern as an RBI-prescribed indicator."


def _missing_evidence(context: dict) -> list[str]:
    live = context.get("live_account_context", {})
    missing = []
    if not live.get("recent_transactions"):
        missing.append("No relevant account history was retrieved from Cassandra.")
    if not live.get("recent_alerts"):
        missing.append("No previous alerts were retrieved.")
    if not live.get("previous_investigations"):
        missing.append("No previous investigations were retrieved.")
    return missing


def _known_paysim_cases(context: dict) -> list[dict]:
    cases = context.get("historical_paysim_context", {})
    if isinstance(cases, list):
        return cases
    return list(cases.get("fraud_cases", [])) + list(cases.get("normal_cases", []))


def _case_label(case: dict) -> str:
    return str(case.get("label") or case.get("metadata", {}).get("label", "")).lower()


def _case_comparison(case: dict) -> str:
    """Summarize only explicitly present historical fields; never add live model scores."""
    meta = case.get("metadata", {})
    parts = ["Synthetic PaySim " + (_case_label(case) or "unlabeled") + " reference"]
    kind = case.get("transaction_type") or meta.get("transaction_type")
    amount = case.get("amount", meta.get("amount"))
    if kind is not None: parts.append(f"transaction type {kind}")
    if amount is not None: parts.append(f"recorded amount {amount}")
    text = str(case.get("text", ""))
    behaviors = []
    if "origin balance decreased" in text.lower() or meta.get("balance_change_amount", "0") not in ("0", "0.0", 0, 0.0):
        behaviors.append("origin balance decreased")
    if "destination balance increased" in text.lower() or meta.get("destination_balance_increased") is True:
        behaviors.append("destination balance increased")
    if behaviors: parts.append("observed " + " and ".join(behaviors))
    return "; ".join(parts) + ". Similarity does not establish fraud in the current alert."


def _live_behavior(alert: dict) -> str:
    kind = alert.get("transaction_type", alert.get("type", "transaction"))
    amount = alert.get("amount")
    sentence = f"The current {kind} transaction"
    if amount is not None: sentence += f" for amount {amount}"
    old_o, new_o = alert.get("old_balance_orig", alert.get("oldbalanceOrg")), alert.get("new_balance_orig", alert.get("newbalanceOrig"))
    old_d, new_d = alert.get("old_balance_dest", alert.get("oldbalanceDest")), alert.get("new_balance_dest", alert.get("newbalanceDest"))
    movement = []
    if old_o is not None and new_o is not None and old_o != new_o:
        movement.append(f"origin balance moved from {old_o} to {new_o}")
    if old_d is not None and new_d is not None and old_d != new_d:
        movement.append(f"destination balance moved from {old_d} to {new_d}")
    if movement: sentence += " has " + " and ".join(movement)
    return sentence + "."


def _parse_json(raw: str) -> dict:
    if not isinstance(raw, str):
        raise InvestigationSchemaError("LLM response was not text")
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise InvestigationSchemaError("LLM response did not contain a JSON object") from None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            raise InvestigationSchemaError("LLM response contained malformed JSON") from None
    if not isinstance(value, dict):
        raise InvestigationSchemaError("LLM response must be a JSON object")
    return value


def _catalog(context: dict) -> dict[str, tuple[str, dict]]:
    catalog = {}
    alert = context.get("alert", {})
    for alert_id in (alert.get("transaction_id"), alert.get("alert_id")):
        if alert_id: catalog[str(alert_id)] = ("live_transaction", alert)
    if alert.get("transaction_id"):
        catalog["model-output:" + str(alert["transaction_id"])] = ("model_output", context.get("model_output", alert))
    if not alert.get("transaction_id") and not alert.get("alert_id"):
        catalog["current-alert"] = ("live_transaction", alert)
    live = context.get("live_account_context", {})
    for key in ("recent_transactions", "recent_alerts", "previous_investigations"):
        for item in live.get(key, []):
            for id_key in ("transaction_id", "alert_id", "investigation_id"):
                if item.get(id_key):
                    catalog[str(item[id_key])] = ("cassandra_history", item)
                    break
    for group, typ in (("regulatory_context", "rbi_knowledge"),):
        for item in context.get(group, []):
            sid = item.get("document_id")
            if sid: catalog[str(sid)] = (typ, item)
    paysim = context.get("historical_paysim_context", {})
    if isinstance(paysim, list):
        cases = paysim
    else:
        cases = paysim.get("fraud_cases", []) + paysim.get("normal_cases", [])
    for item in cases:
        sid = item.get("document_id") or item.get("source_row_id")
        if sid:
            label = str(item.get("label") or item.get("metadata", {}).get("label", "")).lower()
            catalog[str(sid)] = ("paysim_fraud" if label == "fraud" else "paysim_normal", item)
    return catalog


def _normalize(model_result: dict, context: dict, model: str) -> dict:
    alert, catalog = context.get("alert", {}), _catalog(context)
    evidence = []
    for item in model_result.get("evidence", []):
        if not isinstance(item, dict): continue
        sid, source_type = str(item.get("source_id", "")), item.get("source_type")
        known = catalog.get(sid)
        if not known or known[0] != source_type: continue
        finding = _guard_customer_claim(_safe_regulatory_claim(_guard_historical_model_leak(_guard_claim(str(item.get("finding", "")).strip()), context), context), context)
        if source_type in {"paysim_fraud", "paysim_normal"}:
            source_text = json.dumps(known[1], ensure_ascii=False).lower()
            if any(field in finding.lower() and field not in source_text for field in MODEL_FIELDS):
                continue
            finding = "Synthetic PaySim context only; similarity does not establish fraud in the current alert. " + finding
        evidence.append({"source_type": source_type, "source_id": sid, "finding": finding})
    paysim_cases = _known_paysim_cases(context)
    actual_cases = {str(x.get("document_id") or x.get("source_row_id")): x for x in paysim_cases}
    raw_comparison = model_result["historical_comparison"]
    if isinstance(raw_comparison, dict):
        comparison_items = [(x, "fraud_cases") for x in raw_comparison.get("fraud_cases", [])] + [(x, "normal_cases") for x in raw_comparison.get("normal_cases", [])]
    else:
        comparison_items = [(x, "fraud_cases" if str(x.get("label", "")).lower() == "fraud" else "normal_cases") for x in raw_comparison]
    comparisons = {"fraud_cases": [], "normal_cases": []}
    for item, group in comparison_items:
        if not isinstance(item, dict): continue
        sid = str(item.get("source_id", "")); source = actual_cases.get(sid)
        if source:
            actual_group = "fraud_cases" if _case_label(source) == "fraud" else "normal_cases"
            claim = str(item.get("comparison", ""))
            source_text = json.dumps(source, ensure_ascii=False).lower()
            if any(field in claim.lower() and field not in source_text for field in MODEL_FIELDS):
                continue
            comparisons[actual_group].append({"source_id": sid, "comparison": _guard_customer_claim(_safe_regulatory_claim(_guard_historical_model_leak(_guard_claim(claim), context), context), context) + " Similarity does not establish fraud in the current alert."})
    for case in paysim_cases:
        sid = str(case.get("document_id") or case.get("source_row_id") or "")
        group = "fraud_cases" if _case_label(case) == "fraud" else "normal_cases"
        if sid and not any(item["source_id"] == sid for item in comparisons[group]):
            comparisons[group].append({"source_id": sid, "comparison": _case_comparison(case)})
    regulatory = {str(x.get("document_id")): x for x in context.get("regulatory_context", []) if x.get("document_id")}
    references = []
    for item in model_result["regulatory_references"]:
        if not isinstance(item, dict): continue
        source = regulatory.get(str(item.get("source_id", "")))
        if source:
            meta = source.get("metadata", {})
            authority = meta.get("authority", source.get("authority"))
            status = meta.get("status", source.get("status"))
            current = meta.get("current_authority", source.get("current_authority"))
            source_type = meta.get("source_type", source.get("source_type"))
            reference = _safe_regulatory_claim(str(item.get("reference", "")), context)
            if "RBI" in reference and not (authority == "RBI" and current is True and status == "current" and source_type == "primary_regulatory"):
                reference = "Reference retained without current RBI attribution because retrieved authority metadata is not verified. " + reference
            references.append({"source_id": str(source["document_id"]), "source_file": meta.get("source_file", source.get("source")),
                "source_pages": meta.get("source_pages"), "authority": authority, "status": status,
                "current_authority": current, "source_type": source_type, "reference": reference})
    # Keep a minimal, source-linked description of retrieved regulatory text even
    # when a small local model omits citations from otherwise valid JSON.
    referenced = {item["source_id"] for item in references}
    for source in context.get("regulatory_context", []):
        meta = source.get("metadata", {})
        flat_text = re.sub(r"\s+", " ", str(source.get("text", "")))
        source_text = str(source.get("text", ""))
        if (not source.get("document_id") or source["document_id"] in referenced or
                meta.get("authority", source.get("authority")) != "RBI" or
                meta.get("source_type", source.get("source_type")) != "primary_regulatory" or
                meta.get("status", source.get("status")) != "current" or
                meta.get("current_authority", source.get("current_authority")) is not True or
                not re.search(r"EWS|Early Warning Signals", flat_text, re.I) or
                not re.search(r"RFA|Red Flagging of Accounts", flat_text, re.I) or
                not re.search(r"monitoring|unusual activities", flat_text, re.I)):
            continue
        references.append({"source_id": str(source["document_id"]), "source_file": meta.get("source_file", source.get("source")),
            "source_pages": meta.get("source_pages"), "authority": "RBI", "version": meta.get("version", source.get("version")),
            "status": meta.get("status", source.get("status")), "current_authority": meta.get("current_authority", source.get("current_authority")),
            "source_type": meta.get("source_type", source.get("source_type")),
            "reference": "Retrieved text discusses EWS/RFA, alert triggers, validation, real-time monitoring, transactional data, and unusual activities; it does not by itself define the current transaction's balance movements as an RBI-prescribed indicator."})
    def strings(key):
        value = model_result.get(key, [])
        if not isinstance(value, list):
            return []
        return [_guard_customer_claim(_safe_regulatory_claim(_guard_historical_model_leak(_guard_claim(x.strip()), context), context), context) for x in value if isinstance(x, str) and x.strip()]
    supplied = json.dumps(context, ensure_ascii=False).lower()
    review_points = []
    customer_attributes = ("occupation", "location", "city", "kyc", "ip address", "device", "customer intent", "transaction purpose", "beneficiary relationship")
    for point in strings("recommended_review_points"):
        unsupported = [attribute for attribute in customer_attributes if attribute in point.lower() and attribute not in supplied]
        if unsupported:
            review_points.append("Review applicable customer/account information available to the authorized investigator.")
        else:
            review_points.append(point)
    if not review_points:
        review_points.append("Review applicable customer/account information available to the authorized investigator.")
    uncertainty = strings("uncertainties")
    probability = alert.get("xgboost_probability")
    if probability is not None:
        uncertainty.append(f"XGBoost probability {probability} is a model estimate, not certainty; review the underlying evidence.")
    missing = list(dict.fromkeys(strings("missing_evidence") + _missing_evidence(context)))
    counter = [x for x in strings("counter_evidence") if not any(token in x.lower() for token in ("no relevant account history", "no previous alerts", "no previous investigations", "no history exists", "no alerts exist", "not retrieved", "not available"))]
    for item in comparisons["normal_cases"]:
        counter.append("Retrieved normal synthetic PaySim reference: " + item["comparison"])
    risk_factors = strings("risk_factors")
    if alert.get("risk_level") is not None:
        risk_factors.append(f"The current alert has supplied risk level {alert['risk_level']}.")
    if alert.get("anomaly_score") is not None:
        risk_factors.append(f"The current alert has Isolation Forest anomaly score {alert['anomaly_score']}.")
    if alert.get("xgboost_probability") is not None:
        risk_factors.append(f"The current alert has XGBoost probability {alert['xgboost_probability']}.")
    risk_factors.append(_live_behavior(alert))
    evidence = list(evidence)
    txid = str(alert.get("transaction_id") or alert.get("alert_id") or "current-alert")
    live_finding = _live_behavior(alert)
    if not any(x["source_type"] == "live_transaction" and x["source_id"] == txid for x in evidence):
        evidence.append({"source_type": "live_transaction", "source_id": txid, "finding": live_finding})
    if alert.get("anomaly_score") is not None or alert.get("xgboost_probability") is not None or alert.get("risk_level") is not None:
        evidence.append({"source_type": "model_output", "source_id": "model-output:" + txid,
            "finding": "; ".join(x for x in risk_factors if "current alert" in x.lower())})
    for source in context.get("regulatory_context", []):
        if source.get("document_id"):
            evidence.append({"source_type": "rbi_knowledge", "source_id": str(source["document_id"]),
                "finding": "Retrieved regulatory text; see its source-linked regulatory reference."})
    live = context.get("live_account_context", {})
    for key, id_keys in (("recent_transactions", ("transaction_id",)), ("recent_alerts", ("alert_id", "transaction_id")),
                         ("previous_investigations", ("investigation_id", "alert_id"))):
        for record in live.get(key, []):
            sid = next((str(record[name]) for name in id_keys if record.get(name)), None)
            if not sid:
                continue
            facts = [f"{name}={record[name]}" for name in ("event_time", "transaction_type", "type", "amount", "risk_level", "investigation_status") if record.get(name) is not None]
            evidence.append({"source_type": "cassandra_history", "source_id": sid,
                "finding": "Retrieved Cassandra " + key.replace("_", " ") + " record" + (": " + ", ".join(facts) if facts else ".")})
    for case in paysim_cases:
        sid = str(case.get("document_id") or case.get("source_row_id") or "")
        if sid:
            label = "paysim_fraud" if _case_label(case) == "fraud" else "paysim_normal"
            evidence.append({"source_type": label, "source_id": sid, "finding": _case_comparison(case)})
    if missing:
        evidence.append({"source_type": "missing_evidence", "source_id": "retrieval:cassandra", "finding": "; ".join(missing)})
    status_values = context.get("retrieval_status", {}).values()
    status = "completed" if all(value == "success" for value in status_values) and not missing else ("partial" if any(value == "success" for value in status_values) else "insufficient_evidence")
    summary = _guard_customer_claim(_safe_regulatory_claim(_guard_claim(model_result["investigation_summary"].strip(), summary=True), context), context)
    if summary.lower().startswith("analyze the evidence") or len(summary.split()) < 8:
        score_note = ", ".join(x for x in (f"risk level {alert.get('risk_level')}" if alert.get("risk_level") is not None else None,
            f"anomaly score {alert.get('anomaly_score')}" if alert.get("anomaly_score") is not None else None,
            f"XGBoost probability {alert.get('xgboost_probability')}" if alert.get("xgboost_probability") is not None else None) if x)
        classes = sorted({"fraud" if _case_label(case) == "fraud" else "normal" for case in paysim_cases})
        history_note = "Retrieved synthetic PaySim " + " and ".join(classes) + " cases provide contextual comparison; similarity does not establish fraud in the current alert." if classes else "No PaySim comparison cases were retrieved."
        regulatory_note = "Retrieved RBI primary material discusses EWS/RFA and transaction monitoring, but does not establish that this exact balance pattern is fraudulent or a prescribed indicator." if references else "No regulatory reference was retrieved."
        summary = f"The current alert is {score_note or 'under review'} according to supplied model outputs. {_live_behavior(alert)} {regulatory_note} {history_note}"
    result = {"investigation_id": str(uuid.uuid4()), "alert_id": str(alert.get("alert_id", "")),
        "transaction_id": str(alert.get("transaction_id", "")), "generated_at": datetime.now(timezone.utc).isoformat(),
        "investigation_summary": summary, "alert_assessment": alert_assessment(alert),
        "evidence": evidence, "risk_factors": list(dict.fromkeys(risk_factors)), "counter_evidence": list(dict.fromkeys(counter)), "missing_evidence": missing,
        "historical_comparison": comparisons, "regulatory_references": references, "uncertainties": list(dict.fromkeys(uncertainty)),
        "recommended_review_points": list(dict.fromkeys(review_points)), "investigation_status": status,
        "llm_model": model, "rag_version": str(context.get("rag_version", "kb_v2"))}
    return validate_result(result)


def investigate_context(context: dict, llm=None, debug_response_path: str | Path | None = None) -> dict:
    try:
        provider = llm or create_llm_provider("gemini")
    except LLMProviderError as exc:
        return failure_result(context.get("alert", {}), "gemini", str(context.get("rag_version", "kb_v2")), exc.category)
    model = getattr(provider, "model", "unknown")
    system, user = build_messages(context)
    raw = None
    with DURATION.labels("investigation", "llm_and_validation").time():
        try:
            raw = provider.generate(user, system_prompt=system)
            payload = validate_llm_payload(_parse_json(raw))
            result = _normalize(payload, context, model)
            count("llm", "generation", "success")
            return result
        except LLMProviderError as exc:
            count("llm", "generation", "timeout" if exc.category == "llm_timeout" else "failure")
            LOGGER.warning("LLM investigation failed category=%s", exc.category)
            result = failure_result(context.get("alert", {}), model, str(context.get("rag_version", "kb_v2")), exc.category)
        except (InvestigationSchemaError, KeyError, TypeError, ValueError) as exc:
            count("llm", "generation", "invalid_response")
            LOGGER.warning("LLM response validation failed category=%s", type(exc).__name__)
            result = failure_result(context.get("alert", {}), model, str(context.get("rag_version", "kb_v2")),
                "invalid_model_response", missing_key=exc.missing_key, invalid_field=exc.invalid_field)
        if debug_response_path and result["investigation_status"] == "failed":
            path = Path(debug_response_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Only the raw model response is written; prompts and credentials are never included.
            path.write_text(str(raw or "<provider returned no response>"), encoding="utf-8")
    result["investigation_id"] = str(uuid.uuid4())
    return result


def investigate_file(path: str | Path, llm=None, repository=None, persist: bool = True) -> dict:
    source = Path(path)
    context = json.loads(source.read_text(encoding="utf-8"))
    source_alert = context.get("alert", {})
    is_synthetic_offline = source_alert.get("source") == "rag_test" or str(source_alert.get("alert_id", "")).startswith("rag_test_")
    debug_path = source.parent / f"debug_llm_response_{source_alert.get('alert_id', source.stem)}.txt" if is_synthetic_offline else None
    result = investigate_context(context, llm, debug_response_path=debug_path)
    stem = source.stem[:-8] if source.stem.endswith("_context") else source.stem
    destination = source.with_name(f"{stem}_result.json")
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if persist:
        from rag.investigation.investigation_service import InvestigationRepository
        repo = repository or InvestigationRepository()
        try: repo.save(result, context)
        finally:
            if repository is None: repo.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate a structured LLM investigation from a RAG context artifact")
    parser.add_argument("context_json")
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()
    result = investigate_file(args.context_json, persist=not args.no_persist)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
