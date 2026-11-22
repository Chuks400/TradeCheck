import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import (review_pdfs, review_texts, number, description_similarity,
                    compare_values, measure, parse_document_date)
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

    def test_unit_spellings_are_read(self):
        self.assertEqual('match', compare_values('gross_kg', '850 KGS', '850')[0])
        self.assertEqual((6000, 'pcs'), measure('500 DOZ'))
        self.assertEqual('match', compare_values('quantity', '500 DOZ', '6000 pcs')[0])
        # A missing unit must never be assumed for a converting unit.
        self.assertEqual('review', compare_values('quantity', '500 DOZ', '500')[0])
        # Valid data in a unit this prototype cannot convert stays a warning.
        self.assertEqual('review', compare_values('quantity', '5,000 shirts', '5000 pcs')[0])

    def test_company_name_normalisation(self):
        self.assertEqual('match', compare_values('consignee', 'Harbor Retail USA L.L.C.',
                                                  'Harbor Retail USA LLC')[0])
        self.assertEqual('match', compare_values('consignee', 'Harbor  Retail USA, LLC',
                                                  'Harbor Retail USA LLC')[0])
        # Ltd and LLC are different entity types: a person decides, no auto-pass.
        self.assertEqual('review', compare_values('consignee', 'Harbor Retail USA Ltd',
                                                   'Harbor Retail USA LLC')[0])

    def test_dates_are_not_guessed(self):
        self.assertEqual((None, 'ambiguous'), parse_document_date('05/11/2026'))
        self.assertEqual('ok', parse_document_date('18 Nov 2026')[1])
        self.assertEqual('ok', parse_document_date('2026年11月18日')[1])

    def test_unreadable_value_is_amber_not_red(self):
        invoice = ('Invoice No: INV-1\nInvoice Date: 2026-11-18\nDescription of Goods: Shorts\n'
                   'Quantity (pcs): 5000\nCartons: 100\nGross Weight (kg): heavy\n'
                   'Net Weight (kg): 800\nCountry of Origin: China')
        packing = invoice.replace('Gross Weight (kg): heavy', 'Gross Weight (kg): 850')
        r = review_texts(invoice, packing)
        self.assertEqual('amber', r['status'])
        self.assertTrue(any(i['code'] == 'UNREADABLE_VALUE' and i['severity'] == 'amber'
                            for i in r['issues']))
        self.assertFalse(any(i['code'] == 'INVALID_NUMBER' for i in r['issues']))

    def test_skipped_total_check_is_visible(self):
        invoice = ('Invoice No: INV-1\nInvoice Date: 2026-11-18\nDescription of Goods: Shorts\n'
                   'Quantity (pcs): 5000\nUnit Price (USD): N/A\nTotal Value (USD): 22500.00\n'
                   'Cartons: 100\nGross Weight (kg): 850\nNet Weight (kg): 800\n'
                   'Country of Origin: China')
        packing = ('Invoice No: INV-1\nDescription of Goods: Shorts\nQuantity (pcs): 5000\n'
                   'Cartons: 100\nGross Weight (kg): 850\nNet Weight (kg): 800\n'
                   'Country of Origin: China')
        r = review_texts(invoice, packing)
        self.assertTrue(any(i['code'] == 'CHECK_SKIPPED' and i['severity'] == 'amber'
                            for i in r['issues']))

if __name__=='__main__':
    unittest.main()
