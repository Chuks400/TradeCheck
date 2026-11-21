"""Summarize independently observed manual-vs-TradeCheck timings and issues.

Input is a CSV of actual measurements, not fake or inferred benchmark results.
Usage: python evaluation/summarize.py evaluation/measurements.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import mean

REQUIRED = (
    "case_id", "dataset_type", "ground_truth_issues",
    "manual_detected_issues", "tradecheck_detected_issues",
    "manual_seconds", "tradecheck_total_seconds",
)


def ids(value):
    return {item.strip().lower() for item in (value or "").split(";") if item.strip()}


def counts(rows, name):
    tp = fp = fn = 0
    for row in rows:
        correct = ids(row["ground_truth_issues"])
        detected = ids(row[name])
        tp += len(correct & detected)
        fp += len(detected - correct)
        fn += len(correct - detected)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"TP": tp, "FP": fp, "FN": fn, "precision": precision, "recall": recall, "F1": f1}


def score(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not set(REQUIRED).issubset(reader.fieldnames or []):
            raise ValueError("CSV missing required columns: " + ", ".join(sorted(set(REQUIRED) - set(reader.fieldnames or []))))
        rows = list(reader)
    if not rows:
        raise ValueError("No measured cases found. Fill the worksheet with actual observations.")
    seen = set()
    for row in rows:
        if not row["case_id"].strip() or row["case_id"] in seen:
            raise ValueError("Each case must have a unique nonblank case_id.")
        seen.add(row["case_id"])
        if row["dataset_type"].strip().lower() not in {"synthetic", "external"}:
            raise ValueError("dataset_type must be 'synthetic' or 'external'.")
        for key in ("manual_seconds", "tradecheck_total_seconds"):
            try:
                row[key] = float(row[key])
            except (ValueError, TypeError):
                raise ValueError(f"{row['case_id']}: enter a numeric value for {key}.")
            if row[key] < 0:
                raise ValueError(f"{row['case_id']}: {key} cannot be negative.")
    result = {
        "document_sets": len(rows),
        "data_sources": {kind: sum(r["dataset_type"].strip().lower() == kind for r in rows)
                         for kind in ("synthetic", "external")},
        "manual_avg_seconds": mean(r["manual_seconds"] for r in rows),
        "tradecheck_avg_total_seconds": mean(r["tradecheck_total_seconds"] for r in rows),
        "manual_detection": counts(rows, "manual_detected_issues"),
        "tradecheck_detection": counts(rows, "tradecheck_detected_issues"),
    }
    return result


def fmt(value):
    return "N/A" if value is None else f"{value:.1%}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python evaluation/summarize.py path/to/measurements.csv")
    try:
        stats = score(sys.argv[1])
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
    print(f"Measured document sets: {stats['document_sets']} (synthetic: {stats['data_sources']['synthetic']}; external: {stats['data_sources']['external']})")
    print(f"Mean manual total time: {stats['manual_avg_seconds']:.2f}s")
    print(f"Mean TradeCheck total time: {stats['tradecheck_avg_total_seconds']:.2f}s")
    for name in ("manual", "tradecheck"):
        metric = stats[name + "_detection"]
        print(f"{name.title()}: TP={metric['TP']}, FP={metric['FP']}, FN={metric['FN']}, precision={fmt(metric['precision'])}, recall={fmt(metric['recall'])}, F1={fmt(metric['F1'])}")
    if stats["data_sources"]["external"] == 0:
        print("WARNING: All evaluated documents are synthetic. Do not claim real-world accuracy.")
