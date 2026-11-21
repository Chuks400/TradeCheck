"""Regression tests for optional draft documents, with fictional text only."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extended_review import review_bundle_texts, SYNTHETIC_EXTRAS

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


class ExtendedReviewTests(unittest.TestCase):
    def test_base_unchanged(self):
        result = review_bundle_texts(INVOICE, PACKING)
        self.assertEqual("green", result["status"])
        self.assertEqual([], result["extra_comparisons"])

    def test_clean_draft_documents(self):
        result = review_bundle_texts(INVOICE, PACKING, SYNTHETIC_EXTRAS["clean"])
        self.assertEqual("green", result["status"])
        self.assertGreater(len(result["extra_comparisons"]), 5)

    def test_draft_bill_carton_mismatch(self):
        result = review_bundle_texts(INVOICE, PACKING, SYNTHETIC_EXTRAS["bol_cartons_error"])
        self.assertEqual("red", result["status"])
        self.assertTrue(any(i["field"] == "cartons" and "bill of lading" in i["label"].lower()
                            for i in result["issues"]))

    def test_origin_certificate_mismatch(self):
        result = review_bundle_texts(INVOICE, PACKING, SYNTHETIC_EXTRAS["coo_origin_error"])
        self.assertEqual("red", result["status"])
        self.assertTrue(any(i["field"] == "origin" for i in result["issues"]))

    def test_reject_unsupported_kind(self):
        with self.assertRaises(ValueError):
            review_bundle_texts(INVOICE, PACKING, {"customs_declaration": "text"})

    def test_unknown_format_is_not_approved(self):
        result = review_bundle_texts(INVOICE, PACKING, {"bol": "Unreadable unlabelled text"})
        self.assertEqual("amber", result["status"])


if __name__ == "__main__":
    unittest.main()
