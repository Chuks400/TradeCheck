"""Evaluate the self-generated demo cases; NOT a real-world accuracy benchmark."""
from pathlib import Path
import json
from engine import review_pdfs
from make_samples import CASES

root = Path(__file__).resolve().parent
expected = {
    'clean':'green', 'quantity_error':'red','invoice_error':'red','origin_error':'red',
    'multiple_errors':'red','description_review':'amber','bad_invoice_total':'red'
}
records = []
for case in CASES:
    ident=case['id']
    inv=(root/'samples'/f'{ident}_invoice.pdf').read_bytes()
    pack=(root/'samples'/f'{ident}_packing.pdf').read_bytes()
    result=review_pdfs(inv,pack,{'source':'SYNTHETIC TEST'})
    records.append({'scenario':ident,'expected':expected[ident],'actual':result['status'],
                    'status_as_expected':expected[ident]==result['status'],
                    'flags':result['summary']['flags'],
                    'checks':result['summary']['checks'],
                    'processing_ms':result['summary']['processing_ms'],
                    'issue_codes':[i['code'] for i in result['issues']]})
summary={'notice':'SELF-GENERATED, SYNTHETIC DEMO CASES ONLY. NOT A FIELD ACCURACY MEASUREMENT OR A MANUAL TIME-SAVINGS COMPARISON.',
         'scenarios':len(records), 'status_expected_correct':sum(r['status_as_expected'] for r in records),
         'manual_baseline_measured':False,
         'results':records}
(root/'results').mkdir(exist_ok=True)
(root/'results'/'demo_validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('Synthetic scenarios:',summary['scenarios'],'expected statuses matched:',summary['status_expected_correct'])
