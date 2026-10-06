from tools.evaluate_llm_providers import assess


def test_evaluation_flags_unsupported_personal_facts_and_scores_missing_evidence():
    evidence = [{
        "source_type": "authoritative_current_transaction",
        "source_id": "TX-1",
        "content": {"amount": 100.0},
    }]
    response = {
        "answer": "The customer's occupation is an engineer; that information is not present in evidence.",
        "evidence": evidence,
        "missing_evidence": ["Occupation is not present in retrieved evidence."],
    }

    scores = assess("What is the customer's occupation?", response, evidence)

    assert scores["missing_evidence_acknowledged"] == 1.0
    assert "occupation" in scores["unsupported_claim_flags"]
