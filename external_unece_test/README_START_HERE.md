# UNECE public-example evaluation package for TradeCheck v0.3

**Source:** https://unvtd.unece.org/implementation/example-trade/

This package contains the four **original, unchanged UNECE fictional JSON files** in `source/`, and four **clearly derived, aggregated labelled-text views** in `for_tradecheck/` that you can paste into TradeCheck v0.3. These are independently published public examples; **not actual Shenzhou International data** and not a sample of real company shipments.

## Quick method — browser

1. Open TradeCheck v0.3 at your running local address (e.g. http://127.0.0.1:8766).
2. Select **Paste document text**.
3. Open `for_tradecheck/invoice.txt` and paste all its lines into **Invoice Text**.
4. Open `for_tradecheck/packing.txt` and paste all its lines into **Packing Text**.
5. Paste `for_tradecheck/bol.txt` into **Draft bill of lading** and `for_tradecheck/coo.txt` into **Certificate of origin draft**.
6. Run once with **Use local LLM** OFF, download JSON and take a screenshot.
7. Run again with **Use local LLM** ON, using `qwen2.5:3b`, download JSON and take a screenshot.
8. Record the results: original dataset source, fields checked, issues flagged, wrong/missing fields, time. A field-level assessment must be verified against the unchanged JSON and PDF examples.

## Alternative — run without copying/pasting

Extract the `external_unece_test` folder directly into the **TradeCheck repository folder**, so it is at:

`E:\TradeCheck_AI_Document_Review_Prototype\TradeCheck\external_unece_test`

Then, in PowerShell:

```powershell
cd "E:\TradeCheck_AI_Document_Review_Prototype\TradeCheck"
py external_unece_test\run_tradecheck.py
py external_unece_test\run_tradecheck.py --llm
```

The outputs are in `external_unece_test/results/rules_only.json` and `llm_enabled.json`.

To reproduce all derived text files and independent checks from the original UNECE JSON files:

```powershell
py external_unece_test\prepare_unece.py
```

## What the source-grounding checks show

`reference_checks.csv` contains **15 checks** of facts in the original JSON files, including invoice IDs, purchase order, bill-of-lading ID, packages, shipment weights, total goods quantity, quantities for each SKU, product-level gross weights and invoice arithmetic. All 15 checks matched on the source files used to construct this package. These checks are performed *independently of TradeCheck*.

The shared shipment is for **250 units** across four products, **6 packages**, **520 kg gross**, **475 kg net**, country of origin `VN`. Invoice number is `INV-2025-031-001`.

## Important research integrity notes

- **These are transformed data, not raw document extraction.** The original source has 4 product lines; the derived labelled text uses aggregate values. TradeCheck v0.3 supports a single product line and doesn't natively upload JSON. Use the experiment to study its **consistency-check pipeline on externally sourced values**, NOT to measure raw JSON parsing or multi-line extraction accuracy.
- **No carton count on invoice.** The source invoice has a shipping-mark range but no explicit number of cartons. We did NOT invent `Cartons: 6` on its behalf. TradeCheck may flag a required field as missing even though the trade invoice isn't necessarily defective.
- **Different consignee roles.** The source bill of lading consignee is `Pacific Trade Bank Ltd` while the invoice and packing list consignee is `Wave Rider Supplies Pty Ltd`. The invoice states documentary-credit payment terms. TradeCheck may label this a mismatch, but it is **not automatically an actual business error**. Treat it as a human-review item / potential false positive.
- **The products are mixed.** The four product names are joined into a single 'Description of Goods' in the derived text; this loses line-item structure. The packing item quantities are summed across 6 packages.
- If the local model extracts zero extra fields from the derived text, this is expected: the normalized field labels are already simple. Do not claim an LLM performance improvement on this experiment.
- Backend processing time doesn't include human verification and file handling. Do not claim overall time savings without measuring the full workflow.
- Do not upload the derived results to a public repo as if they were real shipment records or independent benchmark accuracy. Check UNECE's usage/reuse terms before redistribution beyond this research exercise.
- The UNECE UNVTD website indicates its standard is under development as of Nov 2026. Do not call it a finalized production standard.

## Research report description (adapt as needed)

> A separate external-consistency exercise used one independently published, fictional UNECE UNVTD trade example comprising commercial invoice, packing list, bill of lading, and certificate of origin records. The original JSON documents were retained, while a documented Python transformation projected shared fields into the single-record text format supported by the TradeCheck v0.3 prototype. Fifteen source-level reference checks were consistent. The TradeCheck results were assessed separately, and the dataset was not treated as real enterprise shipment data or an independent measure of raw document-extraction accuracy.

Update that paragraph with the actual TradeCheck results after running the commands above.
