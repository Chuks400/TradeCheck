"""Regression tests for optional draft documents, with fictional text only."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extended_review import review_bundle_pdfs, review_bundle_texts, SYNTHETIC_EXTRAS

ROOT = Path(__file__).resolve().parents[1]

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

    def test_clean_customs_declaration(self):
        result = review_bundle_texts(INVOICE, PACKING, SYNTHETIC_EXTRAS["clean"])
        self.assertEqual("green", result["status"])
        self.assertIn("decl", result["extra_fields"])
        self.assertEqual("6109100000", result["extra_fields"]["decl"]["hs_code"])

    def test_declaration_hs_mismatch_on_first_six_digits(self):
        invoice = INVOICE.replace("Country of Origin: China", "HS Code: 6109.10\nCountry of Origin: China")
        result = review_bundle_texts(invoice, PACKING, SYNTHETIC_EXTRAS["decl_hs_error"])
        self.assertEqual("red", result["status"])
        self.assertTrue(any(i["field"] == "hs_code" and i["severity"] == "red"
                            for i in result["issues"]))

    def test_declaration_cannot_post_date_the_export(self):
        result = review_bundle_texts(INVOICE, PACKING, SYNTHETIC_EXTRAS["decl_date_error"])
        self.assertEqual("red", result["status"])
        self.assertTrue(any(i["code"] == "DECLARATION_AFTER_EXPORT" for i in result["issues"]))

    def test_declaration_term_difference_is_flagged(self):
        invoice = INVOICE.replace("Country of Origin: China", "Terms of Delivery: FOB\nCountry of Origin: China")
        result = review_bundle_texts(invoice, PACKING, SYNTHETIC_EXTRAS["decl_terms_review"])
        self.assertEqual("red", result["status"])
        self.assertTrue(any(i["field"] == "terms" for i in result["issues"]))

    def test_carton_count_not_compared_for_other_packaging(self):
        decl = SYNTHETIC_EXTRAS["clean"]["decl"].replace("包装种类: 纸箱", "包装种类: 托盘")
        result = review_bundle_texts(INVOICE, PACKING, {"decl": decl})
        self.assertEqual("amber", result["status"])
        self.assertTrue(any(i["field"] == "cartons" and i["severity"] == "amber"
                            for i in result["issues"]))

    def test_declaration_pdf_upload_is_readable(self):
        result = review_bundle_pdfs(
            (ROOT / "samples" / "clean_invoice.pdf").read_bytes(),
            (ROOT / "samples" / "clean_packing.pdf").read_bytes(),
            {"decl": (ROOT / "samples" / "declaration_draft.pdf").read_bytes()},
        )
        self.assertEqual("green", result["status"])
        self.assertEqual("6109100000", result["extra_fields"]["decl"]["hs_code"])


if __name__ == "__main__":
    unittest.main()
