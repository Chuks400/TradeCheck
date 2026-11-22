"""Run TradeCheck on derived, independent UNECE fictional-example data.

Place the external_unece_test folder in the TradeCheck repository beside app.py.
  py external_unece_test\run_tradecheck.py
  py external_unece_test\run_tradecheck.py --llm
The source JSON remains unmodified. Does not prove raw-JSON parsing performance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0,str(REPO))


def main():
    parser = argparse.ArgumentParser(description='Independent UNECE sample: derived text, not raw-JSON extraction benchmark.')
    parser.add_argument('--llm',action='store_true',help='Ask local Ollama for optional field extraction')
    parser.add_argument('--model',default='qwen2.5:3b')
    args=parser.parse_args()
    if not (REPO/'extended_review.py').exists():
        raise SystemExit('Place external_unece_test directory inside your TradeCheck repository, beside app.py.')
    from llm_review import review_with_local_llm
    docs = {k: (ROOT/'for_tradecheck'/f'{k}.txt').read_text(encoding='utf-8')
            for k in ('invoice','packing','bol','coo')}
    result=review_with_local_llm(docs['invoice'],docs['packing'],
       {'bol':docs['bol'],'coo':docs['coo']},
       metadata={'source':'UNECE UNVTD published fictional sample: lossy, aggregated text projection from original JSON',
                 'raw_json_extraction_evaluated':False,'input_document_count':4},
       use_llm=args.llm,model=args.model)
    filename='llm_enabled.json' if args.llm else 'rules_only.json'
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results'/filename).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Output:',ROOT/'results'/filename)
    print('LLM status:',result['llm']['status'])
    print('Fields supplemented:',result['llm']['added_fields'])
    print('Status:',result['status'])
    print('Checks:',result['summary']['checks'])
    print('Issues flagged:',result['summary']['flags'])
    print('Processing (backend only):',result['summary']['processing_ms'],'ms')
    print('Detected issues:')
    for issue in result['issues']:
        print('  -',issue['severity'].upper(),issue['label'],':',issue['code'])
    print('IMPORTANT: The invoice has no carton count; bill-of-lading consignee is a bank.')
    print('A RED status does not prove an actual error in these public examples.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
