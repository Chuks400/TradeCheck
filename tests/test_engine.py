import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import review_pdfs, review_texts, number, description_similarity
from make_samples import OUTPUT


def sample(name):
    return review_pdfs((OUTPUT / f'{name}_invoice.pdf').read_bytes(),
                       (OUTPUT / f'{name}_packing.pdf').read_bytes(),
                       {'source':'synthetic'})


class ReviewEngineTests(unittest.TestCase):
    def test_clean(self):
        r=sample('clean')
        self.assertEqual('green',r['status'])
        self.assertEqual(0,r['summary']['flags'])
        self.assertEqual('5000',r['invoice_fields']['quantity'])

    def test_quantity_error(self):
        r=sample('quantity_error')
        self.assertEqual('red',r['status'])
        self.assertTrue(any(i['field']=='quantity' and i['code']=='CROSS_DOCUMENT_MISMATCH' for i in r['issues']))

    def test_invoice_number_mismatch(self):
        r=sample('invoice_error')
        self.assertTrue(any(i['field']=='invoice_number' for i in r['issues']))

    def test_origin_mismatch(self):
        r=sample('origin_error')
        self.assertTrue(any(i['field']=='origin' for i in r['issues']))

    def test_multiple_errors(self):
        r=sample('multiple_errors')
        self.assertEqual(4,r['summary']['critical'])

    def test_description_warns_human(self):
        r=sample('description_review')
        self.assertEqual('amber',r['status'])
        self.assertTrue(any(i['code']=='DESCRIPTION_REVIEW' for i in r['issues']))

    def test_invoice_calculation(self):
        r=sample('bad_invoice_total')
        self.assertTrue(any(i['code']=='INVOICE_TOTAL_ERROR' for i in r['issues']))

    def test_missing_fields_flagged(self):
        r=review_texts('Invoice No: X\nQuantity (pcs): 5', 'Invoice No: X\nQuantity (pcs): 5')
        self.assertEqual('red',r['status'])
        self.assertTrue(any(i['code']=='MISSING_REQUIRED_FIELD' for i in r['issues']))

    def test_scanned_pdf_fails_visible(self):
        r=review_texts('', '')
        self.assertEqual('red',r['status'])
        self.assertTrue(any(i['code']=='NO_EXTRACTABLE_TEXT' for i in r['issues']))

    def test_wrong_weight(self):
        r=review_texts('Invoice No: X\nInvoice Date: 2026-11-18\nDescription of Goods: Shorts\nQuantity (pcs): 5\nCartons: 1\nGross Weight (kg): 10\nNet Weight (kg): 11\nCountry of Origin: China',
                       'Invoice No: X\nDescription of Goods: Shorts\nQuantity (pcs): 5\nCartons: 1\nGross Weight (kg): 10\nNet Weight (kg): 11\nCountry of Origin: China')
        self.assertEqual('red',r['status'])
        self.assertTrue(any(i['code']=='WEIGHT_RULE' for i in r['issues']))

    def test_numeric_parser(self):
        self.assertEqual(number('12,000.50 USD'),number('12000.5'))
        self.assertIsNone(number('not a number'))

if __name__=='__main__':
    unittest.main()
