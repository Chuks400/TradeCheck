# Competition evaluation: manual vs TradeCheck

This folder records **observed** results. Do not turn demo timings into claims about real efficiency.

## Fair test design

1. Collect invoice and packing-list pairs you have permission to use. Optional draft bill of lading and origin certificate pairs may be added. Remove private identifiers.
2. Establish ground-truth issues with an independent careful review. Use consistent issue IDs such as `quantity`, `invoice_number`, `origin`. Each ID should name one independently verifiable error.
3. Give the same documents to a human reviewer who does **not** know the answers. Record all errors they identify and time the entire review with a stopwatch.
4. Run TradeCheck on the same documents. Record its errors and **total operator time**, including upload, reading warnings, and saving the report. Do not use `processing_ms` as a substitute for total time.
5. Record one row per document set in `measurements.csv` (copy `measurements_template.csv`). Use semicolons to separate issue IDs. If no issues are present, leave the cell blank.
6. Run `python evaluation/summarize.py evaluation/measurements.csv`.

Fields: `case_id`, `dataset_type` (`synthetic` or `external`), `ground_truth_issues`, `manual_detected_issues`, `tradecheck_detected_issues`, `manual_seconds`, `tradecheck_total_seconds`.

The script calculates mean total seconds per document set plus **precision, recall and F1** for both methods. Detected issue IDs must match the ground-truth naming scheme. A human should judge whether individual outputs describe the same issue before entering the measurements.

**Do not commit real shipment documents, private identifiers, or measurements containing sensitive data.** The empty template is tracked, but `evaluation/measurements.csv` is excluded from Git.

## Limitations

- A demo-only experiment shows the prototype handles its own examples; it is not a real-world accuracy benchmark.
- With small samples, results are preliminary. State sample count and source clearly.
- Human timing can vary with experience. If possible, test multiple reviewers and randomize review order.
- Traffic/customs accuracy and full Shenzhou company performance are not established by these measurements.
