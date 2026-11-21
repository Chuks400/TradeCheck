"""Run a REAL local-Ollama end-to-end test with all four fictional documents.

Requires Ollama installed locally and: ollama pull qwen2.5:3b
Usage: python llm_live_smoke.py
This script is separate from CI because it downloads no models.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from engine import extract_pdf_text
from extended_review import SYNTHETIC_EXTRAS
from llm_review import DEFAULT_MODEL, review_with_local_llm

ROOT = Path(__file__).resolve().parent

def main() -> int:
    invoice = extract_pdf_text((ROOT / "samples" / "clean_invoice.pdf").read_bytes())
    packing = extract_pdf_text((ROOT / "samples" / "clean_packing.pdf").read_bytes())
    result = review_with_local_llm(
        invoice, packing, SYNTHETIC_EXTRAS["both_errors"],
        metadata={"source": "FICTIONAL FOUR-DOCUMENT LIVE LLM SMOKE TEST"},
        use_llm=True, model=os.environ.get("TRADECHECK_LLM_MODEL", DEFAULT_MODEL),
    )
    meta = result["llm"]
    print("LLM status:", meta["status"])
    print("Model:", meta["model"])
    print("Documents processed by local LLM:", meta["documents_processed"])
    print("Fields supplemented:", meta["added_fields"])
    print("Review status:", result["status"])
    print("Critical mismatches:", result["summary"]["critical"])
    print("Total backend processing:", result["summary"]["processing_ms"], "ms")
    if meta["warning"]:
        print("WARNING:", meta["warning"])
    if meta["status"] != "applied" or meta["documents_processed"] != 4:
        print("FAIL: The local LLM did not run on all four documents.")
        return 1
    if result["status"] != "red" or result["summary"]["critical"] < 2:
        print("FAIL: Expected seeded draft-document discrepancies were not found.")
        return 1
    print("PASS: Real local LLM was called on all four documents; the rule engine flagged the seeded mismatches.")
    print("This is only a synthetic demonstration, not a real-world accuracy measurement.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
