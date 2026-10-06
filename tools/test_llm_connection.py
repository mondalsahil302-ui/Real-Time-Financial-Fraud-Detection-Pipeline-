"""Check the configured Gemini provider reachability without logging credentials."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from rag.investigation.llm_provider import LLMProviderError, create_llm_provider


def main() -> int:
    load_dotenv(ROOT / ".env")
    provider = None
    try:
        provider = create_llm_provider("gemini")
        result = provider.check_connection()
    except LLMProviderError as exc:
        print(f"LLM check failed: {exc}")
        return 1
    finally:
        if provider is not None:
            provider.close()
    print(f"Provider: {result['provider']}\nModel: {result['model']}\nStatus: {result['status']}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
