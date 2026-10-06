"""Run the checked-in synthetic RAG context through the configured local LLM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from rag.investigation.llm_investigator import investigate_file


def main() -> int:
    context = ROOT / "rag_output" / "investigations" / "rag_test_transfer_context.json"
    result = investigate_file(context, persist=False)
    print("===== INVESTIGATION RESULT =====")
    for label, key in (("Investigation ID", "investigation_id"), ("Alert ID", "alert_id"), ("Transaction ID", "transaction_id"),
                       ("Summary", "investigation_summary"), ("Risk Factors", "risk_factors"), ("Counter Evidence", "counter_evidence"),
                       ("Historical Comparison", "historical_comparison"), ("Regulatory References", "regulatory_references"),
                       ("Uncertainties", "uncertainties"), ("Recommended Review Points", "recommended_review_points"),
                       ("Investigation Status", "investigation_status"), ("LLM Model", "llm_model")):
        print(f"\n{label}:\n{json.dumps(result.get(key), ensure_ascii=False, indent=2)}")
    print(f"\nResult file: {context.with_name('rag_test_transfer_result.json')}")
    return 0 if result["investigation_status"] != "failed" else 1


if __name__ == "__main__": raise SystemExit(main())
