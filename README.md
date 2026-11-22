# TradeCheck Lab — AI-Assisted Trade Document Review (MVP v0.3)

**Student competition prototype for Topic 2: AI-Enabled Optimization of International Supply Chain Business Processes.**

TradeCheck checks one **commercial invoice** against one **packing list** before they are issued, and can optionally compare a **draft bill of lading**, **draft certificate of origin** and **draft customs declaration**. It flags differences in quantities, weights, countries of origin, invoice identifiers, and missing key fields. A lightweight NLP similarity model checks whether the two product descriptions appear similar enough or need human review. Results appear in a browser with red/amber/green triage, an issue list, and an exportable comparison report.

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
- **Document comparison:** Match invoice number, PO reference, quantity, cartons, gross/net weight, origin, HS number, consignee, currency, delivery terms and product description.
- **Basic rules:** Check invoice total = quantity × unit price and gross weight >= net weight.
- **Completeness:** Flag missing required fields.
- **Triage:** Red = clear mismatch or invalid field; amber = needs human interpretation or could not be read; green = none of the implemented checks detected an issue.
- **Optional draft documents:** Detect shared-field inconsistencies in bills of lading, certificates of origin and customs declarations; these are advisory comparisons, not legal checks.
- **Exports:** Download JSON review record or a CSV of comparison results, including optional draft comparisons.

### Is it AI?

TradeCheck has three complementary layers:

- **Deterministic checks** compare numbers, dates, references and documents. These remain the decision layer.
- **Basic NLP** uses character n-gram TF-IDF for similar product descriptions.
- **Optional local LLM** via Ollama extracts candidate fields from less familiar text layouts. It does **not** decide whether trade documents are legally valid. Suggested values are only used if they can be found in the source text, and every result needs human confirmation.

Without Ollama the original rule-based/NLP prototype still works. With Ollama installed, the system uses a real local language model, not an API simulation. **LLM tests in CI use mocks**; the separate live smoke test invokes the actual downloaded model on your own machine.

No customs rulings, legal approvals, document issuance or cloud LLM services are included. OCR of scanned PDFs is still outside the scope.

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



## Set up a real local LLM (optional — Windows)

1. Install **Ollama** from [ollama.com/download](https://ollama.com/download). Open the Ollama application.
2. Open PowerShell and download the model once:

   ```powershell
   ollama pull qwen2.5:3b
   ollama list
   ```

   Qwen2.5 3B is approximately **1.9 GB** to download. It runs locally; slower PCs may take longer to process each document.
3. Start TradeCheck normally using `start_windows.bat` or `python app.py --open`.
4. Check **Use local LLM for field extraction** in the document-review screen. Keep model name `qwen2.5:3b`.
5. Try **Correct documents** with **Incorrect carton count on bill of lading** under the optional extended test, then click **Run document checks**.
6. Read the LLM status above the results. **LOCAL LLM ACTIVE** confirms that the local model ran. **LLM UNAVAILABLE** means it did not run and deterministic checks were used instead.

For an automated four-document **real LLM** smoke test, run from the project folder:

```powershell
python llm_live_smoke.py
```

This test runs the model against four **fictional** documents and checks for two seeded discrepancies. It is **not** evidence of accuracy on independent company documents. Do not report its measurements as real-world human time savings.

### Privacy and limitations

The Python backend sends document text to **127.0.0.1:11434** (the local Ollama process) only when you enable the LLM. It does not use a paid API key or upload document text to a remote LLM provider. Only text-based PDFs are supported; the LLM cannot OCR scanned images. Model-suggested field values must appear in the source text, but this does not guarantee they were extracted from the correct section or that the resulting documents are compliant. An employee must always verify the original documents.


## Optional draft-document checks (v0.2)

Under **Try demo documents**, choose an additional fictional scenario to test a correct draft bundle, a wrong carton count on the bill of lading, an incorrect origin in the draft certificate, or a customs declaration with a wrong HS code, different delivery terms, or a declaration date after the export date. The original seven invoice/packing list PDF examples remain unchanged. The optional demo drafts are **generated as fictional labelled text** inside `extended_review.py`.

Under **Upload your PDFs**, the bill of lading, certificate and customs declaration are optional. They must be text-based PDFs whose fields appear as `Label: value` lines; `samples/declaration_draft.pdf` is a fictional example with Chinese labels. The engine compares fields present in both documents; it does **not** decide certificate authenticity, tariff eligibility, final origin, or legal compliance. HS codes are compared on the first six digits only, and an unknown field or unusual layout (such as a real declaration printed as a colon-free table) is flagged for manual review rather than silently approved.

## Measured competition experiment

The [evaluation guide](evaluation/README.md) includes a blank CSV template and a small script for calculating manual vs TradeCheck review times, precision, recall and F1 from **actual observations**. Include upload and human follow-up time in the TradeCheck stopwatch measurement. Internal `processing_ms` is only code time, not a complete workflow measure. Do not report the synthetic examples as real-world accuracy or proof of Shenzhou's internal error rates.

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
- **Optional drafts:** Basic field comparisons only; no authenticated documents or binding legal rulings.
- **Declaration scope:** The draft declaration is compared on shared fields, declaration date vs export date, and the first six HS digits. Statutory units, packaging codes, customs release and duty calculation are outside the tested MVP.
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
- `extended_review.py` – optional draft-document checks and fictional demo draft data.
- `llm_review.py` – optional local Ollama field extraction and rule-engine fallback.
- `llm_live_smoke.py` – command-line test against a real locally installed model.
- `evaluation/` – blank worksheet and scoring script for observed manual-versus-tool results.
- `tests/` – automated checks.
- `research_context.md` – verified figures from supplied Shenzhou reports.

This prototype is meant to support a focused **pre-issuance invoice vs packing-list** competition experiment, not all trade-document processing at once.
