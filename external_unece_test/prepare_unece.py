"""Prepare auditable text projections of four publicly released UNECE fictional JSON documents.

Does NOT change source files, infer missing fields, or create fake errors.
Creates a source-to-field mapping for TradeCheck v0.3's single-line, labelled-text input.
This is a normalization test (not a raw-JSON extraction benchmark).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import csv, hashlib, json

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'source'
OUT = ROOT / 'for_tradecheck'
OUT.mkdir(exist_ok=True)

NAMES = {'invoice':'commercial-invoice-example.json', 'packing':'packing-list-example.json',
         'bol':'bill-of-lading-example.json','coo':'certificate-of-origin-example.json'}
raw = {k: json.loads((SRC / v).read_text(encoding='utf-8')) for k,v in NAMES.items()}
sub = {k:v['credentialSubject'] for k,v in raw.items()}
i,p,b,c = [sub[k] for k in ('invoice','packing','bol','coo')]


def amt(x):
    if isinstance(x,dict):
        x = x['amount']
    return Decimal(str(x))


def nice(x):
    return format(x.normalize(), 'f') if isinstance(x, Decimal) else str(x)


def text_of_lines(s):
    return '; '.join(s)


def inv_products():
    return [a['product']['name'] for a in i['itemsShipped']]


def pack_products():
    by_sku = {}
    for package in p['packages']:
        for item in package['items']:
            by_sku.setdefault(item['sku'], item['description'])
    return [by_sku[line['sku']] for line in i['itemsShipped']]


pack_qty = defaultdict(int)
for package in p['packages']:
    for item in package['items']:
        pack_qty[item['sku']] += item['quantity']

rows = {
  'invoice': [
    ('Invoice No', i['invoiceNumber']),
    ('Invoice Date', i['invoiceDate']),
    ('Purchase Order', i['purchaseOrderNumber']),
    ('Consignee', i['consignee']['name']),
    ('Description of Goods', text_of_lines(inv_products())),
    ('Quantity (pcs)', sum(row['itemCount'] for row in i['itemsShipped'])),
    # Invoice contains NO explicit package/carton count: do not invent one!
    ('Gross Weight (kg)', sum(amt(row['grossWeight']) for row in i['itemsShipped'])),
    ('Net Weight (kg)', sum(amt(row['netWeight']) for row in i['itemsShipped'])),
    ('Country of Origin', i['originCountry']),
    ('HS Code', i['itemsShipped'][0]['commodity']),
    ('Total Invoice Value (USD)', amt(i['totalAmount'])),
  ],
  'packing': [
    ('Invoice No', p['invoiceNumber']),
    ('Purchase Order', p['purchaseOrderNumber']),
    ('Consignee', p['consignee']['name']),
    ('Description of Goods', text_of_lines(pack_products())),
    ('Quantity (pcs)', sum(pack_qty.values())),
    ('Cartons', p['totalPackages']),
    ('Gross Weight (kg)', amt(p['totalGrossWeight'])),
    ('Net Weight (kg)', amt(p['totalNetWeight'])),
    ('Country of Origin', p['originCountry']['addressCountry']),
    ('HS Code', p['packages'][0]['items'][0]['hsCode']),
  ],
  'bol': [
    ('Consignee', b['consignee']['name']), # Bank consignee differs legitimately: manual review required
    ('Description of Goods', text_of_lines([g['description'] for g in b['goods']])),
    ('Quantity (pcs)', sum(amt(g['quantity']) for g in b['goods'])),
    ('Cartons', b['numberOfPackages']),
    ('Gross Weight (kg)', amt(b['grossWeight'])),
  ],
  'coo': [
    ('Invoice No', c['invoiceNumber']),
    ('Consignee', c['consignee']['name']),
    ('Description of Goods', text_of_lines([g['description'] for g in c['goods']])),
    ('Quantity (pcs)', sum(amt(g['quantity']) for g in c['goods'])),
    ('Country of Origin', c['originCountry']['addressCountry']),
  ],
}

for kind, fieldrows in rows.items():
    path = OUT / f'{kind}.txt'
    path.write_text('\n'.join(f'{key}: {nice(value)}' for key,value in fieldrows)+'\n',encoding='utf-8')

checks = []
def add(name, fieldvals, explanation=''):
    # Normalised comparison (without flattening role semantic differences).
    values = [nice(v) for v in fieldvals.values()]
    checks.append({'check': name, 'result':'MATCH' if len(set(values)) == 1 else 'REVIEW',
                   'values': fieldvals, 'notes': explanation})

add('invoice_number', {'invoice':i['invoiceNumber'], 'packing':p['invoiceNumber'], 'coo':c['invoiceNumber']})
add('purchase_order', {'invoice':i['purchaseOrderNumber'], 'packing':p['purchaseOrderNumber']})
add('bill_of_lading_number', {'invoice':i['billOfLadingNumber'], 'bol':b['billOfLadingNumber']})
add('packages', {'packing':p['totalPackages'], 'bol':b['numberOfPackages'], 'coo':c['numberOfPackages']})
add('gross_weight_kg', {
 'invoice_sum':nice(sum(amt(z['grossWeight']) for z in i['itemsShipped'])),
 'packing_header':nice(amt(p['totalGrossWeight'])),
 'packing_packages_sum':nice(sum(amt(z['grossWeight']) for z in p['packages'])),
 'bol':nice(amt(b['grossWeight'])),
 'coo_sum':nice(sum(amt(z['grossWeight']) for z in c['goods'])),
})
add('net_weight_kg', {
 'invoice_sum':nice(sum(amt(z['netWeight']) for z in i['itemsShipped'])),
 'packing_header':nice(amt(p['totalNetWeight'])),
 'packing_packages_sum':nice(sum(amt(z['netWeight']) for z in p['packages'])),
 'coo_sum':nice(sum(amt(z['netWeight']) for z in c['goods']))})
add('total_goods_quantity', {
 'invoice':sum(z['itemCount'] for z in i['itemsShipped']),
 'packing':sum(pack_qty.values()),
 'bol':nice(sum(amt(z['quantity']) for z in b['goods'])),
 'coo':nice(sum(amt(z['quantity']) for z in c['goods']))})
add('origin_country', {'invoice':i['originCountry'], 'packing':p['originCountry']['addressCountry'], 'coo':c['originCountry']['addressCountry']})
for item in i['itemsShipped']:
    add('sku_quantity_'+item['sku'], {'invoice':item['itemCount'], 'packing':pack_qty[item['sku']]})
add('gross_by_product', {
 'invoice':','.join(nice(amt(z['grossWeight'])) for z in i['itemsShipped']),
 'bol':','.join(nice(amt(z['grossWeight'])) for z in b['goods']),
 'coo':','.join(nice(amt(z['grossWeight'])) for z in c['goods']),
})
add('invoice_subtotal', {'sum_of_lines':nice(sum(amt(z['lineTotal']) for z in i['itemsShipped'])),
  'invoice_subtotal':nice(amt(i['subtotal']))})
expected_total = amt(i['subtotal']) + amt(i['freightCost']) + amt(i['insuranceCost']) - sum(amt(z['amount']) for z in i['allowanceCharges'])
add('invoice_total_including_adjustments', {'calculated':nice(expected_total), 'invoice_total':nice(amt(i['totalAmount']))})

meta = {
 'dataset': 'UNECE UNVTD example trade (fictional shared shipment)',
 'dataset_type': 'independent public sample, NOT real company records',
 'provenance': 'https://unvtd.unece.org/implementation/example-trade/',
 'source_files': {v:{'sha256':hashlib.sha256((SRC/v).read_bytes()).hexdigest()} for v in NAMES.values()},
 'method': 'Lossy, explicit aggregate projection from 4 multi-line-item source JSON files into TradeCheck v0.3 labelled text fields',
 'source_checks':checks,
 'important_limitations':[
   'These summaries are NOT the original JSON; they are derived input projections.',
   'TradeCheck v0.3 lacks native JSON and multi-line-item support; summary comparisons cannot measure raw JSON extraction accuracy.',
   'Invoice has no explicit carton-count field: do not silently infer it from packing.',
   'Bill of lading consignee is Pacific Trade Bank Ltd while invoice consignee is Wave Rider Supplies Pty Ltd; this may be legitimate for documentary-credit shipments, not necessarily an error.',
   'Country code VN is kept verbatim; TradeCheck normalizes it to Vietnam.',
   'This dataset is a single fictional shipment, so do not compute or claim real-world model accuracy.',
 ]
}
(ROOT/'reference_checks.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
with (ROOT/'reference_checks.csv').open('w',newline='',encoding='utf-8-sig') as f:
    wr=csv.writer(f)
    wr.writerow(['check','result','reference_values','notes'])
    for row in checks:
        wr.writerow([row['check'],row['result'],json.dumps(row['values'],ensure_ascii=False),row['notes']])
print('Created four TradeCheck text projections.')
print('Independent-source checks:',len(checks),'match:',sum(x['result']=='MATCH' for x in checks),
 'review:',sum(x['result']=='REVIEW' for x in checks))
