"""Local LLM integration tests. No paid API or live Ollama required in CI."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_review import (
    LLMUnavailable, _parse_extraction, ollama_extract_fields,
    review_with_local_llm,
)
from extended_review import SYNTHETIC_EXTRAS

INVOICE = """Invoice No: INV-2026-001
Invoice Date: 2026-11-18
Description of Goods: Cotton knitted T-shirts
Quantity (pcs): 5000
Cartons: 100
Gross Weight (kg): 850
Net Weight (kg): 800
Country of Origin: China
"""
PACKING = """Invoice No: INV-2026-001
Description of Goods: Cotton knitted T-shirts
Quantity (pcs): 5000
Cartons: 100
Gross Weight (kg): 850
Net Weight (kg): 800
Country of Origin: China
"""


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *unused):
        return False
    def read(self, size=-1):
        return json.dumps(self.payload).encode("utf-8")


class LocalLLMReviewTests(unittest.TestCase):
    def test_original_rules_still_work_without_model(self):
        r = review_with_local_llm(INVOICE, PACKING)
        self.assertEqual("green", r["status"])
        self.assertEqual("disabled", r["llm"]["status"])
        self.assertEqual(0, r["llm"]["documents_processed"])

    def test_model_is_called_on_every_document(self):
        calls = []
        def fake(text, model):
            calls.append((text, model))
            return {"invoice_number": "INV-2026-001"}
        r = review_with_local_llm(
            INVOICE, PACKING, SYNTHETIC_EXTRAS["clean"],
            use_llm=True, model="test-local:3b", extractor=fake,
        )
        self.assertEqual("green", r["status"])
        self.assertEqual("applied", r["llm"]["status"])
        self.assertEqual(5, r["llm"]["documents_processed"])
        self.assertEqual(5, len(calls))
        self.assertGreaterEqual(r["summary"]["processing_ms"], r["summary"]["rule_check_ms"])

    def test_llm_enriches_unlabelled_invoice_reference(self):
        invoice = INVOICE.replace("Invoice No: INV-2026-001", "Customer reference INV-2026-001")
        def fake(text, model):
            return {"invoice_number": "INV-2026-001"} if "Customer reference" in text else {}
        r = review_with_local_llm(invoice, PACKING, use_llm=True, extractor=fake)
        self.assertEqual("green", r["status"])
        self.assertEqual("INV-2026-001", r["invoice_fields"]["invoice_number"])
        self.assertEqual(["invoice_number"], r["llm"]["added_fields"]["invoice"])

    def test_model_cannot_invent_missing_number(self):
        invoice = INVOICE.replace("Invoice No: INV-2026-001", "Reference not available")
        def fake(text, model):
            return {"invoice_number": "INV-999"} if text == invoice else {}
        r = review_with_local_llm(invoice, PACKING, use_llm=True, extractor=fake)
        self.assertEqual("red", r["status"])
        self.assertNotIn("invoice_number", r["invoice_fields"])
        self.assertEqual([], r["llm"]["added_fields"]["invoice"])

    def test_llm_failure_falls_back_without_false_success(self):
        def failed(text, model):
            raise LLMUnavailable("Local Ollama unavailable; rule-only checking was used.")
        r = review_with_local_llm(INVOICE, PACKING, use_llm=True, extractor=failed)
        self.assertEqual("fallback", r["llm"]["status"])
        self.assertEqual("green", r["status"])
        self.assertEqual(0, r["llm"]["documents_processed"])
        self.assertIn("rule-only", r["llm"]["warning"])

    def test_mixed_four_document_errors_are_detected(self):
        def fake(text, model):
            return {"invoice_number": "INV-2026-001"}
        r = review_with_local_llm(
            INVOICE, PACKING, SYNTHETIC_EXTRAS["both_errors"],
            use_llm=True, extractor=fake,
        )
        self.assertEqual("red", r["status"])
        self.assertGreaterEqual(r["summary"]["critical"], 2)
        self.assertEqual("applied", r["llm"]["status"])

    def test_llm_value_can_only_support_amber(self):
        invoice = INVOICE.replace("Cartons: 100", "Packed in 100 cartons")
        packing = PACKING.replace("Cartons: 100", "Cartons: 92")
        def fake(text, model):
            return {"cartons": "100"} if "Packed in 100 cartons" in text else {}
        r = review_with_local_llm(invoice, packing, use_llm=True, extractor=fake)
        self.assertEqual("amber", r["status"])
        item = next(i for i in r["issues"] if i["field"] == "cartons")
        self.assertEqual("amber", item["severity"])
        self.assertIn("extracted by the local model", item["detail"])
        self.assertEqual("llm", r["field_sources"]["invoice"]["cartons"])

    def test_guard_drops_exporter_identical_to_consignee(self):
        def fake(text, model):
            if text == INVOICE:
                return {"exporter": "Harbor Retail USA LLC", "consignee": "Harbor Retail USA LLC"}
            return {}
        r = review_with_local_llm(INVOICE, PACKING, use_llm=True, extractor=fake)
        self.assertNotIn("exporter", r["invoice_fields"])
        self.assertTrue(any("identical to the consignee" in note for note in r["llm"]["guards"]))

    def test_ollama_json_schema_request_local_only(self):
        source = "Unlabelled reference INV-2026-001 and origin China"
        body = {"message": {"content": json.dumps({
            "fields": {"invoice_number": "INV-2026-001", "origin": "China",
                       "quantity": "99999", "bad_field": "X"}
        })}}
        def fake_urlopen(request, timeout):
            self.assertEqual("http://127.0.0.1:11434/api/chat", request.full_url)
            sent = json.loads(request.data.decode("utf-8"))
            self.assertFalse(sent["stream"])
            self.assertEqual(0, sent["options"]["temperature"])
            self.assertIsInstance(sent["format"], dict)
            return FakeResponse(body)
        with patch("llm_review.urlopen", fake_urlopen):
            values = ollama_extract_fields(source, "qwen2.5:3b")
        self.assertEqual("INV-2026-001", values["invoice_number"])
        self.assertEqual("China", values["origin"])
        self.assertNotIn("quantity", values)
        self.assertNotIn("bad_field", values)

    def test_malformed_llm_json_raises_clear_error(self):
        with self.assertRaises(LLMUnavailable):
            _parse_extraction("oops, not json", INVOICE)

    def test_invalid_model_name_is_rejected(self):
        with self.assertRaises(ValueError):
            review_with_local_llm(INVOICE, PACKING, use_llm=True, model="http://evil.test/")


if __name__ == "__main__":
    unittest.main()
