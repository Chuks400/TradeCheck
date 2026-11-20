# TradeCheck Lab — AI-Assisted Trade Document Review (MVP)

**Student competition prototype for Topic 2: AI-Enabled Optimization of International Supply Chain Business Processes.**

TradeCheck checks one **commercial invoice** against one **packing list** before they are finalised. It flags differences in quantities, weights, countries of origin, invoice identifiers, and missing key fields. A lightweight NLP similarity model checks whether the two product descriptions appear similar enough or need human review. Results appear in a browser with red/amber/green triage, an issue list, and an exportable comparison report.

> **Important:** All included sample documents are **fictional** and NOT Shenzhou International's actual shipping documents. The system is a first prototype, not a deployed product or customs-compliance decision tool.

## How to run (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) if needed (check **Add Python to PATH** when installing).
2. Extract the zip file.
3. Double-click **`start_windows.bat`**. It installs the dependencies and starts the application.
4. If it does not open automatically, visit **http://127.0.0.1:8765** in your browser.
5. Select **Try demo documents → Quantity mismatch → Run document checks**.
6. Click **Upload your PDFs** if you have your own text-based PDFs.
7. Press `Ctrl+C` in the command window to close the server.

The app runs on `127.0.0.1` (your own computer) and does not upload document contents to any external server.

## How to run (Mac / Linux)

```bash
cd tradecheck_mvp
python3 -m pip install -r requirements.txt
python3 app.py --open
```

## What it checks

- **Extraction:** Read selectable text from uploaded PDFs (PyMuPDF).
- **Normalisation:** Standardise invoice IDs, decimal numbers and a small set of country names.
- **Document comparison:** Match invoice number, PO reference, quantity, cartons, gross/net weight, origin, HS number, consignee and product description.
- **Basic rules:** Check invoice total = quantity × unit price and gross weight >= net weight.
- **Completeness:** Flag missing required fields.
- **Triage:** Red = clear mismatch or invalid field; amber = needs human interpretation; green = none of the implemented checks detected an issue.
- **Exports:** Download JSON review record or a CSV of comparison results.

### Is it AI?

This is a **hybrid rule-based + NLP-assisted baseline**, rather than a trained generative AI system. It uses `scikit-learn` character n-gram TF-IDF similarity for variable product descriptions. Exact numerical and required-field checks are deterministic for accuracy and auditability. There is **no LLM**, no AI customs/rules judgment, and no automatic submission or issuance. Later versions can add OCR, multilingual entity extraction, a learned text-similarity model and a verified customs rule library.

## Sample test cases

The `samples/` folder contains **14 simulated PDFs** (7 invoice/packing-list pairs):

| Scenario | Expected outcome |
|---|---|
| clean | GREEN |
| quantity_error | RED: quantity mismatch |
| invoice_error | RED: invoice ID mismatch |
| origin_error | RED: origin discrepancy |
| multiple_errors | RED: multiple mismatches and weight problem |
| description_review | AMBER: product description may need human review |
| bad_invoice_total | RED: wrong invoice calculation |

To regenerate them: `python make_samples.py`.

## How to verify the system

From the project folder:

```bash
python -m unittest discover -s tests -v
```

Review **the same 7 document pairs** manually and record who spotted which known errors. Record time taken separately for a fair manual-versus-prototype evaluation. Do **not** invent time savings or error-detection performance. `processing_ms` measures code execution only and **is not** the time saved by human reviewers.

## Scope and known limitations

- **Single line item:** one product type per invoice/packing list.
- **PDF text layer required:** image-only scanned PDFs require OCR, which is not included in this MVP.
- **Template-aware parser:** the sample PDF format is supported; arbitrary real-world layouts need expanded extraction or OCR.
- **No customs rules:** HS classification, origin eligibility, tariffs, expiring certificates and document issuance are outside the tested MVP.
- **No live integrations:** the project does not connect to Shenzhou, its customers, banks, customs, or carriers.
- **No proof of Shenzhou's internal deficiency:** the public company data supports why export operations matter, not that Shenzhou has a high document-error rate.
- **Results are advisory:** a GREEN outcome means no **implemented** check detected a problem, not that documents are compliant.

## Files

- `app.py` – local HTTP server with JSON review endpoint.
- `engine.py` – extraction, parsing, field comparison, NLP similarity and validation.
- `make_samples.py` – reproducible fictional invoice/packing-list generator.
- `web/` – responsive user interface.
- `samples/` – 14 sample PDFs.
- `tests/` – automated checks.
- `research_context.md` – verified figures from supplied Shenzhou reports.

This prototype is meant to support a focused **pre-issuance invoice vs packing-list** competition experiment, not all trade-document processing at once.
