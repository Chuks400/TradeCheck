# TradeCheck Code Guide

**Project:** TradeCheck Lab — AI-Assisted Trade Document Review  
**Prototype version:** MVP v0.3  
**Research context:** Topic 2 — AI-enabled optimization of international supply-chain business processes  
**Repository:** https://github.com/Chuks400/TradeCheck

This guide explains how to navigate the source code, follow one review request through the system, understand the JSON output, and reproduce the included tests. It describes the current prototype; it is not a specification for features that have not been implemented.

## 1. What the prototype does

TradeCheck is a local-first prototype for pre-issuance consistency review. It compares:

- **Required:** one commercial invoice and one packing list.
- **Optional:** one draft bill of lading, one draft certificate of origin, and one draft customs declaration.

It extracts labelled values, normalizes selected formats and units, compares fields that are available in the supplied documents, applies a small set of validation rules, and returns findings for a person to review.

The prototype supports one product line per invoice/packing-list pair. It is an advisory review tool: it does not issue documents, authenticate documents, classify goods under customs law, determine legal origin, calculate duties, or approve shipments.

> **Research-data note:** The bundled demo documents are fictional. The external UNECE example is a published fictional example transformed into labelled text for this prototype. Neither dataset is Shenzhou International's internal shipment data.

## 2. End-to-end processing flow

```text
Browser interface (web/)
        |
        | GET /api/health, GET /api/samples
        | POST /api/review
        v
app.py — local HTTP server
        |
        +-- sample mode: reads generated PDFs from samples/
        |
        +-- upload mode: decodes uploaded PDF data in memory
        |
        +-- text mode: accepts pasted document text
        |
        v
PDF text extraction (engine.py / PyMuPDF)
        |
        v
Optional local field extraction (llm_review.py / Ollama)
        |  OFF: original extracted text goes to the rule engine
        |  ON: model may suggest source-grounded fields missing from parsing
        v
Core checks (engine.py)
        |
        +-- Optional draft checks (extended_review.py)
        |
        v
Structured JSON result
        |
        v
Browser results and downloadable report
```

The LLM is an optional extraction assistant. The deterministic checks remain responsible for comparisons and validation. The LLM is not a separate shipment-approval decision-maker.

## 3. Source-code map

| File or folder | Responsibility |
|---|---|
| `app.py` | Starts the local HTTP server and handles the browser API. Routes sample, PDF-upload and pasted-text review requests. |
| `engine.py` | Core PDF text extraction, label parsing, value normalization, invoice/packing-list comparisons, basic validation rules and result construction. |
| `extended_review.py` | Adds advisory comparisons for draft bills of lading, certificates of origin and customs declarations. |
| `llm_review.py` | Optional local Ollama field extraction, source-text checks, field enrichment, extraction safeguards and rule-only fallback. |
| `make_samples.py` | Generates the fictional invoice, packing-list and customs-declaration demo PDFs. |
| `web/index.html` | Browser interface structure and document-input controls. |
| `web/app.js` | Browser-side interactions, request construction and display/export of review results. |
| `web/style.css` | Interface styling and responsive layout. |
| `samples/` | Fictional labelled PDF test documents; not real company records. |
| `tests/` | Unit, integration and UI-contract tests. |
| `evaluation/` | Blank measurement template and a script for summarizing independently recorded manual-versus-tool observations. |
| `external_unece_test/` | Documented external-example exercise, transformed text inputs, reference checks and saved output JSON. |
| `research_context.md` | Publicly reported Shenzhou company context and explicit notes about what those figures do and do not establish. |
| `requirements.txt` | Python package dependencies. |

### Main function entry points

- `app.py → Handler.do_POST()`: receives a review request and selects the input mode.
- `engine.py → extract_pdf_text()`: reads selectable text from a PDF.
- `engine.py → parse_fields()`: recognizes supported field labels and their values.
- `engine.py → review_texts()`: performs the core invoice/packing-list review and builds the base result.
- `extended_review.py → review_bundle_texts()`: adds checks for any optional draft documents supplied.
- `llm_review.py → review_with_local_llm()`: optionally enriches document text with local model suggestions, then calls the review pipeline.
- `make_samples.py → generate()`: recreates the fictional sample PDFs.
- `evaluation/summarize.py → score()`: calculates summary metrics from a CSV of actual observations.

## 4. Document fields and checks

### Core invoice and packing-list checks

The parser recognizes labelled fields including:

- Invoice number and invoice/document date
- Exporter, consignee and purchase-order reference
- Product description, HS code and country of origin
- Quantity, cartons, gross weight and net weight
- Unit price, invoice total, currency and delivery terms

The required-field lists are defined by `REQUIRED` in `engine.py`. Some fields are required in one document but not the other; for example, gross weight is required on the packing list, not automatically on the invoice.

The comparison logic checks fields only when both documents contain a value. Numeric comparisons use the supported normalization rules. Company-name differences that appear to be legal-suffix or spelling variations can be sent for human review. Product descriptions use character n-gram TF-IDF similarity when scikit-learn is available, with a text-similarity fallback.

Additional core rules include:

- Positive and valid quantity, carton and weight values
- Gross weight must not be lower than net weight when both are available
- Invoice total should equal quantity multiplied by unit price, within the configured tolerance
- Invoice date should be recognizable and should not be unexpectedly in the future

Unit normalization is limited. The code supports selected aliases for kilograms, pieces, cartons, dozens and pounds; it does not convert every possible trade unit.

### Optional draft-document checks

The optional document types are keyed internally as:

| Input document | Internal key | Examples of fields checked |
|---|---|---|
| Draft bill of lading | `bol` | Invoice/PO reference, consignee, description, quantity, cartons and weights |
| Draft certificate of origin | `coo` | Invoice reference, consignee, description, origin and quantity |
| Draft customs declaration | `decl` | Exporter/consignee, PO, HS code, description, quantity, packages, weights, origin, value, currency and terms |

The customs-declaration parser includes Chinese labels. The HS comparison uses the first six digits. Declaration and export dates are checked so that an unreadable or ambiguous date is referred for review and a declaration date later than the export date is flagged.

These are field-consistency checks only. They do not authenticate a bill of lading or certificate, decide customs classification, establish rules of origin, or verify customs release. Optional documents are not mandatory for every review.

## 5. Optional local LLM

The default model name is `qwen2.5:3b`. The application communicates with Ollama at `http://127.0.0.1:11434/api/chat`.

When the LLM option is enabled:

1. The model is asked to return candidate field values in a constrained JSON structure.
2. The code accepts a suggested value only if the value can be found in the original document text.
3. The model fills fields that the deterministic parser did not already identify; it does not overwrite an already parsed value.
4. Guard functions reject selected implausible assignments, including known cases where a CBM value was mistaken for a weight.
5. The normal deterministic review runs on the resulting text.
6. A mismatch that depends on an LLM-supplied value is softened to human review rather than treated as a definitive red finding.

If Ollama is unavailable or the model request fails, the review falls back to the original text and rule-based checks. Check the returned `llm.status` and `llm.warning` fields rather than assuming the model ran.

**Important:** A source-grounded suggestion can still be assigned to the wrong field. LLM-extracted values must be checked against the original document. LLM use does not mean fine-tuning or training the model on company data.

## 6. Understanding the JSON report

The API returns a JSON object. The most useful top-level fields are:

| JSON field | Meaning |
|---|---|
| `status` | Overall triage: `red`, `amber` or `green`. |
| `summary.checks` | Number of checks attempted. |
| `summary.passed` | Number of checks that passed. |
| `summary.flags` | Number of findings raised. |
| `summary.critical` | Count of red findings. |
| `summary.review` | Count of amber findings. |
| `summary.processing_ms` | Backend processing time in milliseconds. It is not total human workflow time. |
| `invoice_fields`, `packing_fields` | Values parsed or supplied to the core review for each required document. |
| `comparisons` | Field-by-field invoice/packing-list comparison results. |
| `issues` | Findings, including severity, code, field, detail, suggested action and source documents. |
| `extra_fields`, `extra_comparisons` | Parsed values and comparisons for optional draft documents, when supplied. |
| `llm` | Whether LLM was enabled, its status/model, documents processed, added fields, safeguards and any warning. |
| `field_sources` | Identifies fields added by the LLM, when any were added. |
| `limitations` | Scope limitations relevant to interpreting the result. |
| `metadata` | Input/source metadata passed by the caller. |

### Triage interpretation

- **RED:** at least one critical mismatch, invalid value, or missing required field was found. Investigate before proceeding.
- **AMBER:** at least one value or comparison needs human interpretation.
- **GREEN:** none of the implemented checks raised an issue.

GREEN does **not** certify that every field was extracted, that all trade requirements were checked, or that a shipment is legally compliant. Always read the issue list, comparisons, field values and limitations—not only the colour.

## 7. Run the application

### Windows

From the extracted project folder in PowerShell:

```powershell
py -m pip install -r requirements.txt
py app.py --port 8766 --open
```

The default port is `8765`; use `--port 8766` if another local process already uses the default. Open the displayed local address in a browser. Stop the server with `Ctrl+C`.

Alternatively, run `start_windows.bat` to install dependencies and start the default configuration.

### macOS / Linux

```bash
python3 -m pip install -r requirements.txt
python3 app.py --open
```

The app binds to `127.0.0.1`, so it is intended for local use on the same computer.

### Optional LLM setup

1. Install and start Ollama.
2. Download the configured model:

   ```powershell
   ollama pull qwen2.5:3b
   ollama list
   ```

3. Start TradeCheck and enable **Use local LLM for field extraction**.
4. Confirm the JSON `llm.status` is `applied`. If it is `fallback`, read `llm.warning`; the deterministic checks still run.

When enabled, document text is sent to the local Ollama process on the same computer. The prototype does not call a hosted LLM API.

## 8. Reproduce tests and sample cases

### Automated test suite

Run from the repository root:

```powershell
py -m unittest discover -s tests -v
```

The suite covers core parsing and validation, optional draft-document checks, LLM safeguards/fallback behavior, API integration using test doubles, and UI contracts. Automated LLM tests use controlled test doubles; they do not prove that a downloaded live model will behave identically on every computer.

### Regenerate fictional PDFs

```powershell
py make_samples.py
```

This recreates the sample invoice/packing-list pairs and the fictional customs declaration under `samples/`.

### Run the external UNECE example exercise

The `external_unece_test/` folder contains instructions, unchanged source JSON examples, derived labelled-text inputs, reference checks and output files. From the repository root:

```powershell
py external_unece_test\run_tradecheck.py
py external_unece_test\run_tradecheck.py --llm
```

The outputs are written to `external_unece_test/results/rules_only.json` and `llm_enabled.json`. Read `external_unece_test/README_START_HERE.md` before interpreting them: the input is a lossy, aggregated text projection of a published fictional example, not raw JSON extraction and not real company shipment data.

## 9. Measuring manual versus prototype review

The `evaluation/measurements_template.csv` and `evaluation/README.md` define the measurement method. Use the same document set for both reviewers and TradeCheck, establish ground-truth issues independently, and record the complete operator time for TradeCheck (upload, reading findings and saving the report).

After entering actual observations in a local `evaluation/measurements.csv`, run:

```powershell
py evaluation/summarize.py evaluation/measurements.csv
```

The script reports average total review times and precision, recall and F1 based on issue IDs. Do not substitute `summary.processing_ms` for stopwatch time. Do not create measurements to fill gaps: leave unrecorded values as unrecorded. The local measurement CSV is excluded from Git to avoid committing potentially sensitive observations.

## 10. Privacy, limits and responsible interpretation

- PDF uploads are decoded and processed in memory by the local application; the server binds to `127.0.0.1`.
- The optional LLM communicates with the local Ollama service at `127.0.0.1:11434`.
- PDF text extraction requires a selectable text layer. Image-only scanned PDFs need OCR, which is not included.
- The prototype supports one product line per invoice/packing-list pair.
- Only the listed labels, fields, units and checks are implemented. Unusual layouts and unsupported values require manual review.
- Optional draft-document checks compare selected fields only and are not legal or customs determinations.
- The public Shenzhou figures in `research_context.md` establish business context; they do not demonstrate that Shenzhou has a particular document-error rate or uses a particular review process.
- Separate fictional, public-example, manually observed and company-reported evidence in the research paper. Never label fictional or public example data as Shenzhou internal data.

For the current scope and additional caveats, also read the main `README.md`, `evaluation/README.md` and `external_unece_test/README_START_HERE.md`.
