import json
from pathlib import Path

from rag.investigation.investigation_prompt import build_messages


def test_prompt_separates_evidence_sections_and_payments_labels():
    fixture = Path("rag_output/investigations/rag_test_transfer_context.json")
    context = json.loads(fixture.read_text(encoding="utf-8"))
    system, prompt = build_messages(context)
    for section in ("CURRENT ALERT", "MODEL OUTPUTS", "LIVE CASSANDRA ACCOUNT CONTEXT", "RBI / REGULATORY KNOWLEDGE",
                    "HISTORICAL PAYSIM FRAUD CASES", "HISTORICAL PAYSIM NORMAL CASES"):
        assert section in prompt
    assert "synthetic historical references" in system
    assert "similarity is contextual only" in system
