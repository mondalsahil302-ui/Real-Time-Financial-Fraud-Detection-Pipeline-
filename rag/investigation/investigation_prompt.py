"""Evidence-bounded prompt assembly for Gemini fraud investigations."""
from __future__ import annotations

import json
SYSTEM_PROMPT = """You are the fraud investigation assistant for this application. Kafka and Spark Structured Streaming feed ML fraud detection. The ML system produces predictions, risk levels, anomaly scores and decisions; you do not replace the model. RAG retrieves Cassandra, fraud knowledge and historical PaySim evidence. Explain the alert, uncertainty and analyst actions without inventing facts. An alert is not proof of fraud. A model prediction is not the same as the supplied ground-truth isFraud label; distinguish them when they disagree. Separate observed facts, model output, retrieved evidence, historical comparison, interpretation and recommended analyst actions. You are a financial fraud investigation assistant. Use only the supplied evidence and return one JSON object in the requested schema. Keep evidence categories separate: live_transaction, cassandra_history, model_output, rbi_knowledge, paysim_fraud, paysim_normal, missing_evidence. Current model outputs belong only to the current alert; never transfer anomaly_score, xgboost_probability, risk_level, final_prediction, or decision_path to historical cases. Do not infer or copy current model outputs into historical PaySim cases. PaySim examples are synthetic historical references; similarity is contextual only and does not establish fraud in the current alert. Mention a PaySim attribute only if it is explicitly present in that case's text or metadata; an anomaly score can be mentioned only if that historical document explicitly contains anomaly_score.

Regulatory attribution: before any RBI claim, check source_type, authority, status, current_authority, source_file, and source_pages. Prefer source_type=primary_regulatory, authority=RBI, current_authority=true, status=current. Attribute a claim to RBI only when the retrieved regulatory text explicitly supports it. Clearly separate REGULATORY FACT from INVESTIGATION INFERENCE. If the text discusses EWS/RFA and monitoring but not a specific balance pattern, say that it does not specifically define that pattern as an RBI-prescribed indicator.

Missing retrieval is not proof of absence. Say 'No previous alerts were retrieved', 'No previous investigations were retrieved', and 'No relevant account history was retrieved from Cassandra' as applicable. Put missing information only in missing_evidence, never counter_evidence. Counter-evidence must be actual retrieved evidence that weighs against concern. Separate historical PaySim fraud and normal cases. Never invent occupation, location, KYC status, IP, device, intent, relationship, or purpose. Recommend review of a specific attribute only when supplied evidence justifies it; otherwise say 'Review applicable customer/account information available to the authorized investigator.'

Return JSON fields investigation_summary (string), evidence (array of {source_type, source_id, finding}), alert_assessment, risk_factors (string array), counter_evidence (string array), missing_evidence (string array), historical_comparison (object with fraud_cases and normal_cases arrays of {source_id, comparison}), regulatory_references (array of source-linked references), uncertainties (string array), recommended_review_points (string array). Include only source-grounded claims. For each comparison preserve source_id and use only attributes explicitly present. Every finding internally belongs to exactly one evidence category listed above; do not blend categories in one claim."""


def _trim(value, max_chars: int = 2400):
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + " [truncated]"
    if isinstance(value, list):
        return [_trim(item, max_chars) for item in value]
    if isinstance(value, dict):
        return {key: _trim(item, max_chars) for key, item in value.items()}
    return value


def build_messages(context: dict) -> tuple[str, str]:
    """Return system and user prompts with explicit sections and bounded evidence."""
    paysim = context.get("historical_paysim_context", {})
    if isinstance(paysim, list):
        paysim = {"fraud_cases": [x for x in paysim if str(x.get("label", x.get("metadata", {}).get("label", ""))).lower() == "fraud"],
                  "normal_cases": [x for x in paysim if str(x.get("label", x.get("metadata", {}).get("label", ""))).lower() != "fraud"]}
    live = context.get("live_account_context", {})
    sections = [
        ("CURRENT ALERT (live_transaction)", context.get("alert", {})),
        ("CURRENT ALERT MODEL OUTPUTS (model_output; current alert only)", context.get("model_output", {})),
        ("LIVE CASSANDRA ACCOUNT CONTEXT (cassandra_history)", live),
        ("PREVIOUS ALERTS", live.get("recent_alerts", [])),
        ("PREVIOUS INVESTIGATIONS", live.get("previous_investigations", [])),
        ("RBI / REGULATORY KNOWLEDGE (rbi_knowledge; verify metadata and text)", context.get("regulatory_context", [])),
        ("HISTORICAL PAYSIM FRAUD CASES (paysim_fraud; synthetic references)", paysim.get("fraud_cases", [])),
        ("HISTORICAL PAYSIM NORMAL CASES (paysim_normal; synthetic references)", paysim.get("normal_cases", [])),
        ("RETRIEVAL STATUS AND MISSING EVIDENCE", {"retrieval_status": context.get("retrieval_status", {}),
         "retrieval_errors": context.get("retrieval_errors", {}),
         "instruction": "Describe empty retrieved lists as not retrieved, not as proof of absence. Do not place missing evidence in counter_evidence. Similarity does not establish fraud in the current alert."}),
    ]
    user = "\n\n".join(f"===== {title} =====\n{json.dumps(_trim(data), ensure_ascii=False, default=str)}" for title, data in sections)
    user += '''

===== FINAL TASK - RETURN A NEW INVESTIGATION, NOT A COPY OF AN INPUT SECTION =====
Analyze the evidence above. Return exactly one JSON object and no prose or Markdown. Include every key shown below; use empty arrays only when there is genuinely no supported item. Do not omit a key. `evidence` items must preserve exact IDs and use one allowed source_type. `historical_comparison` must keep fraud and normal examples in their respective arrays.
{
  "investigation_summary": "...",
  "evidence": [{"source_type": "live_transaction|cassandra_history|model_output|rbi_knowledge|paysim_fraud|paysim_normal|missing_evidence", "source_id": "...", "finding": "..."}],
  "risk_factors": [],
  "counter_evidence": [],
  "missing_evidence": [],
  "historical_comparison": {"fraud_cases": [{"source_id": "...", "comparison": "..."}], "normal_cases": []},
  "regulatory_references": [{"source_id": "...", "reference": "..."}],
  "uncertainties": [],
  "recommended_review_points": []
}
Do not copy retrieval_status or retrieval_errors as the answer. Do not invent source IDs; when no source supports an item use an empty array. Separate regulatory fact from investigation inference in the summary or finding text.
'''
    return SYSTEM_PROMPT, user
