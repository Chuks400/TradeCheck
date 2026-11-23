"""Regression tests for the public Experiment 6 invoice / packing-list layout."""
import unittest
from engine import parse_fields, parse_document_date, compare_values, number
from llm_review import review_with_local_llm

HEADER = """Invoice No.: BIG241014-03                                      Invoice Date.: October 15, 2024
Country of Origin: CHINA                                   L/C Number: TT
P/O No.: 95618169                                                        1,228 EA    3.150/EA    3,868.200
HTS Code.: 9505906000
"""
PACKING = HEADER + """Cargo Description      Quantity   Net Weight   Gross Weight   CBM
P/O No.: 95618169                                   1,228 EA         399.10       516.00       15.500
"""

class Experiment06Tests(unittest.TestCase):
    def test_side_by_side_header_is_not_swallowed(self):
        f = parse_fields(HEADER)
        self.assertEqual("BIG241014-03", f["invoice_number"])
        self.assertEqual("October 15, 2024", f["invoice_date"])
        self.assertEqual("CHINA", f["origin"])
        self.assertEqual("95618169", f["po_number"])
        self.assertEqual("9505906000", f["hs_code"])

    def test_month_first_date_and_each_unit(self):
        self.assertEqual("ok", parse_document_date("October 15, 2024")[1])
        self.assertEqual("match", compare_values("quantity", "1,228", "1,228 EA")[0])
        self.assertEqual("3.150", str(number("3.150/EA")))

    def test_llm_volume_cell_is_not_net_weight(self):
        def extractor(text, model):
            if "CBM" in text:
                return {"quantity": "1,228 EA", "net_kg": "15.500", "gross_kg": "516.00"}
            return {}
        result = review_with_local_llm(HEADER, PACKING, use_llm=True, extractor=extractor)
        self.assertNotIn("net_kg", result["packing_fields"])
        self.assertEqual("516.00", result["packing_fields"]["gross_kg"])
        self.assertTrue(any("CBM" in x for x in result["llm"]["guards"]))

if __name__ == "__main__":
    unittest.main()
