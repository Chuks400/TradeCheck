"""End-to-end local API tests for LLM + all four documents (mocked model)."""
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler
from extended_review import SYNTHETIC_EXTRAS
from llm_review import LLMUnavailable

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


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def review(self, extras):
        data = {
            "mode": "text",
            "invoice_text": INVOICE,
            "packing_text": PACKING,
            "bol_text": extras.get("bol", ""),
            "coo_text": extras.get("coo", ""),
            "use_llm": True,
            "llm_model": "test-local:3b",
        }
        request = Request(
            f"http://127.0.0.1:{self.port}/api/review",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            self.assertEqual(200, response.status)
            return json.loads(response.read().decode("utf-8"))

    def test_four_document_llm_and_rules_together(self):
        def fake(text, model):
            return {"invoice_number": "INV-2026-001"}
        with patch("llm_review.ollama_extract_fields", fake):
            result = self.review(SYNTHETIC_EXTRAS["both_errors"])
        self.assertEqual("applied", result["llm"]["status"])
        self.assertEqual(4, result["llm"]["documents_processed"])
        self.assertEqual("red", result["status"])
        self.assertGreaterEqual(len(result["extra_comparisons"]), 8)
        self.assertTrue(any(x["field"] == "cartons" for x in result["issues"]))
        self.assertTrue(any(x["field"] == "origin" for x in result["issues"]))

    def test_failed_model_reports_rule_only_fallback(self):
        def unavailable(text, model):
            raise LLMUnavailable("Ollama unavailable")
        with patch("llm_review.ollama_extract_fields", unavailable):
            result = self.review(SYNTHETIC_EXTRAS["clean"])
        self.assertEqual("fallback", result["llm"]["status"])
        self.assertEqual("green", result["status"])


if __name__ == "__main__":
    unittest.main()
