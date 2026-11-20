"""Generate fictional, clearly labelled commercial invoices and packing lists."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'samples'
OUTPUT.mkdir(exist_ok=True)

BASE = {
    'invoice_number': 'INV-2026-001',
    'invoice_date': '2026-11-18',
    'exporter': 'Demo Apparel Ltd (FICTIONAL)',
    'consignee': 'Harbor Retail USA LLC (FICTIONAL)',
    'po_number': 'PO-44881',
    'description': 'Cotton knitted T-shirts',
    'hs_code': '6109.10',
    'origin': 'China',
    'quantity': '5000',
    'cartons': '100',
    'gross_kg': '850.0',
    'net_kg': '800.0',
    'unit_price_usd': '4.50',
    'total_value_usd': '22500.00'
}

CASES = [
    {'id': 'clean', 'title': 'Correct documents', 'description': 'All key fields match; a green result is expected.', 'changes_invoice': {}, 'changes_packing': {}},
    {'id': 'quantity_error', 'title': 'Quantity mismatch', 'description': 'Invoice: 5,000 shirts; packing list: 4,800.', 'changes_invoice': {}, 'changes_packing': {'quantity': '4800'}},
    {'id': 'invoice_error', 'title': 'Invoice number mismatch', 'description': 'Packing list refers to the wrong invoice.', 'changes_invoice': {}, 'changes_packing': {'invoice_number': 'INV-2026-099'}},
    {'id': 'origin_error', 'title': 'Origin discrepancy', 'description': 'Invoice says China; packing list says Vietnam.', 'changes_invoice': {}, 'changes_packing': {'origin': 'Vietnam'}},
    {'id': 'multiple_errors', 'title': 'Several errors', 'description': 'Wrong quantity, cartons, and a weight rule failure.', 'changes_invoice': {}, 'changes_packing': {'quantity': '4800', 'cartons': '93', 'gross_kg': '760.0'}},
    {'id': 'description_review', 'title': 'Description difference', 'description': 'Different wording of the product description for NLP review.', 'changes_invoice': {}, 'changes_packing': {'description': 'Mens cotton knit tee shirts'}},
    {'id': 'bad_invoice_total', 'title': 'Incorrect invoice calculation', 'description': 'Invoice amount does not equal quantity times unit price.', 'changes_invoice': {'total_value_usd':'22000.00'}, 'changes_packing': {}},
]

INVOICE_FIELDS = [
    ('Invoice No', 'invoice_number'), ('Invoice Date', 'invoice_date'), ('Exporter', 'exporter'),
    ('Consignee', 'consignee'), ('Purchase Order', 'po_number'), ('Description of Goods', 'description'),
    ('HS Code', 'hs_code'), ('Country of Origin', 'origin'), ('Quantity (pcs)', 'quantity'),
    ('Unit Price (USD)', 'unit_price_usd'), ('Total Value (USD)', 'total_value_usd'),
    ('Cartons', 'cartons'), ('Gross Weight (kg)', 'gross_kg'), ('Net Weight (kg)', 'net_kg'),
]
PACKING_FIELDS = [
    ('Invoice No', 'invoice_number'), ('Document Date', 'invoice_date'), ('Exporter', 'exporter'),
    ('Consignee', 'consignee'), ('Purchase Order', 'po_number'), ('Description of Goods', 'description'),
    ('HS Code', 'hs_code'), ('Country of Origin', 'origin'), ('Quantity (pcs)', 'quantity'),
    ('Cartons', 'cartons'), ('Gross Weight (kg)', 'gross_kg'), ('Net Weight (kg)', 'net_kg'),
]

styles = getSampleStyleSheet()
label_style = ParagraphStyle('Field', parent=styles['Normal'], fontName='Helvetica', fontSize=10,
                             leading=17, spaceAfter=7, textColor=colors.HexColor('#172b4d'))
small_style = ParagraphStyle('SmallDemo', parent=styles['Normal'], fontName='Helvetica', fontSize=9,
                             leading=13, textColor=colors.HexColor('#64748b'))

def make_doc(path, kind, fields):
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=24*mm, leftMargin=24*mm,
                            topMargin=23*mm, bottomMargin=20*mm, title=f'Fictional {kind} Sample')
    flow = []
    flow.append(Paragraph(f'<font color="#123499" size="17"><b>{kind.upper()}</b></font>', styles['Normal']))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph('SYNTHETIC SAMPLE - NOT SHENZHOU INTERNATIONAL DATA',
                          ParagraphStyle('Warning', parent=styles['Normal'], fontName='Helvetica-Bold',
                                         fontSize=9, textColor=colors.HexColor('#b45309'))))
    flow.append(Spacer(1, 9))
    flow.append(HRFlowable(width='100%', color=colors.HexColor('#dbe4f1'), thickness=1))
    flow.append(Spacer(1, 16))
    fieldlist = INVOICE_FIELDS if kind == 'Commercial Invoice' else PACKING_FIELDS
    for label, key in fieldlist:
        flow.append(Paragraph(f'<b>{label}:</b> {fields[key]}', label_style))
    flow.append(Spacer(1, 15))
    flow.append(HRFlowable(width='100%', color=colors.HexColor('#dbe4f1'), thickness=1))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph('Created for the Topic 2 competition prototype. These values are fictional and do not describe real shipments.', small_style))
    doc.build(flow)


def generate():
    for case in CASES:
        inv = {**BASE, **case['changes_invoice']}
        pack = {**BASE, **case['changes_packing']}
        make_doc(OUTPUT / f"{case['id']}_invoice.pdf", 'Commercial Invoice', inv)
        make_doc(OUTPUT / f"{case['id']}_packing.pdf", 'Packing List', pack)
    print(f'Generated {2*len(CASES)} fictional PDFs in {OUTPUT}')

if __name__ == '__main__':
    generate()
