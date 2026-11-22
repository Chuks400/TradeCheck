"""Run a private, offline-ready, local browser interface for TradeCheck Lab.
Usage: python app.py --open  (then visit http://127.0.0.1:8765)
"""
from __future__ import annotations

import argparse
import base64
import binascii
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import mimetypes
import threading
import webbrowser

from engine import MAX_FILE_BYTES, extract_pdf_text
from extended_review import SYNTHETIC_EXTRAS
from llm_review import DEFAULT_MODEL, review_with_local_llm
from make_samples import CASES

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
SAMPLES = ROOT / 'samples'

class Handler(BaseHTTPRequestHandler):
    server_version = 'TradeCheckLocal/0.3'
    def do_GET(self):
        pathname = self.path.split('?')[0]
        if pathname == '/api/samples':
            return self.json_response(200, [{k: v for k, v in c.items() if k not in ('changes_invoice','changes_packing')} for c in CASES])
        if pathname == '/api/health':
            return self.json_response(200, {'ok': True, 'name': 'TradeCheck Lab', 'version': '0.3.0'})
        assets = {'/': 'index.html', '/index.html': 'index.html', '/style.css': 'style.css', '/app.js': 'app.js'}
        if pathname not in assets:
            return self.send_error(404, 'Not found')
        path = WEB / assets[pathname]
        content = path.read_bytes()
        mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') or mime == 'application/javascript' else ''))
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path != '/api/review':
            return self.send_error(404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 4 * MAX_FILE_BYTES * 2 + 20_000:
                raise ValueError('Request is empty or too large.')
            if 'application/json' not in self.headers.get('Content-Type', ''):
                raise ValueError('Expected JSON request.')
            data = json.loads(self.rfile.read(length))
            mode = data.get('mode')
            use_llm = data.get('use_llm') is True
            model = data.get('llm_model') or DEFAULT_MODEL
            if mode == 'sample':
                case = data.get('sample')
                if case not in [c['id'] for c in CASES]:
                    raise ValueError('Unknown sample. Pick one of the listed samples.')
                invoice = (SAMPLES / f'{case}_invoice.pdf').read_bytes()
                packing = (SAMPLES / f'{case}_packing.pdf').read_bytes()
                extra_case = data.get('extra_case') or ''
                if extra_case not in ('', *SYNTHETIC_EXTRAS):
                    raise ValueError('Unknown optional draft-document scenario.')
                result = review_with_local_llm(
                    extract_pdf_text(invoice), extract_pdf_text(packing),
                    SYNTHETIC_EXTRAS.get(extra_case, {}),
                    {'source': 'SYNTHETIC SAMPLE', 'case': case, 'extra_case': extra_case},
                    use_llm=use_llm, model=model,
                )
            elif mode == 'text':
                invoice = data.get('invoice_text', '')
                packing = data.get('packing_text', '')
                extras = {kind: data.get(f'{kind}_text', '') for kind in ('bol', 'coo', 'decl')
                          if str(data.get(f'{kind}_text', '')).strip()}
                if any(not isinstance(t, str) or len(t) > 150_000 for t in [invoice, packing, *extras.values()]):
                    raise ValueError('Text is too long or invalid.')
                result = review_with_local_llm(invoice, packing, extras, {'source': 'USER-PASTED TEXT'}, use_llm=use_llm, model=model)
            elif mode == 'upload':
                def decode(name):
                    encoded = data.get(name, '')
                    if not isinstance(encoded, str) or len(encoded) > MAX_FILE_BYTES * 2:
                        raise ValueError('A PDF file is missing or too large.')
                    try:
                        return base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError):
                        raise ValueError('Invalid PDF data.')
                extras = {kind: decode(f'{kind}_base64') for kind in ('bol', 'coo', 'decl')
                          if data.get(f'{kind}_base64')}
                result = review_with_local_llm(
                    extract_pdf_text(decode('invoice_base64')),
                    extract_pdf_text(decode('packing_base64')),
                    {kind: extract_pdf_text(blob) for kind, blob in extras.items()},
                    {'source': 'USER-UPLOADED PDFS (IN-MEMORY)',
                     'invoice_name': str(data.get('invoice_name', 'invoice.pdf'))[:100],
                     'packing_name': str(data.get('packing_name', 'packing.pdf'))[:100],
                     'optional_docs': list(extras)},
                    use_llm=use_llm, model=model,
                )
            else:
                raise ValueError('Choose sample, upload, or text review.')
            self.json_response(200, result)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            self.json_response(400, {'error': str(e)})
        except Exception:
            self.json_response(500, {'error': 'Document review failed. Please check the file or input format.'})

    def json_response(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Avoid logging user document data. HTTP paths and status codes only.
        print('[local] ' + fmt % args)


def main():
    parser = argparse.ArgumentParser(description='Local-first trade-document review prototype.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open browser automatically')
    args = parser.parse_args()
    if not all((SAMPLES / f"{case['id']}_invoice.pdf").exists() for case in CASES):
        from make_samples import generate
        generate()
    address = ('127.0.0.1', args.port)
    server = ThreadingHTTPServer(address, Handler)
    print(f'\nTradeCheck Lab running at http://127.0.0.1:{args.port}\nPress Ctrl+C to stop. No data is sent to the internet.\n')
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
