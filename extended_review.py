"""Optional draft bill-of-lading and certificate-of-origin checks.

Advisory field consistency only: not a legal or customs decision engine.
The source documents and sample data never leave the local TradeCheck server.
"""
from __future__ import annotations

from time import perf_counter
from decimal import Decimal
from engine import (
    LABELS, clean_value, description_similarity, extract_pdf_text,
    parse_fields, review_texts,
)

DOC_NAMES = {"bol": "Draft bill of lading", "coo": "Draft certificate of origin"}
FIELDS = {
    "bol": ("invoice_number", "po_number", "consignee", "description",
            "quantity", "cartons", "gross_kg", "net_kg"),
    "coo": ("invoice_number", "consignee", "description", "origin", "quantity"),
}
# Every sample below is FICTIONAL and intentionally simple.
SYNTHETIC_EXTRAS = {
    "clean": {
        "bol": "Invoice No: INV-2026-001\nPurchase Order: PO-44881\nConsignee: Harbor Retail USA LLC (FICTIONAL)\nDescription of Goods: Cotton knitted T-shirts\nQuantity (pcs): 5000\nCartons: 100\nGross Weight (kg): 850.0\nNet Weight (kg): 800.0",
        "coo": "Invoice No: INV-2026-001\nConsignee: Harbor Retail USA LLC (FICTIONAL)\nDescription of Goods: Cotton knitted T-shirts\nCountry of Origin: China\nQuantity (pcs): 5000",
    },
}
SYNTHETIC_EXTRAS["bol_cartons_error"] = {
    **SYNTHETIC_EXTRAS["clean"],
    "bol": SYNTHETIC_EXTRAS["clean"]["bol"].replace("Cartons: 100", "Cartons: 92"),
}
SYNTHETIC_EXTRAS["coo_origin_error"] = {
    **SYNTHETIC_EXTRAS["clean"],
    "coo": SYNTHETIC_EXTRAS["clean"]["coo"].replace("Origin: China", "Origin: Vietnam"),
}
SYNTHETIC_EXTRAS["both_errors"] = {
    "bol": SYNTHETIC_EXTRAS["bol_cartons_error"]["bol"],
    "coo": SYNTHETIC_EXTRAS["coo_origin_error"]["coo"],
}


def review_bundle_texts(
    invoice_text: str,
    packing_text: str,
    extras: dict[str, str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Extend the existing review without changing its original result format."""
    start = perf_counter()
    extras = extras or {}
    if any(kind not in DOC_NAMES for kind in extras):
        raise ValueError("Only draft bills of lading and certificates of origin are supported.")
    result = review_texts(invoice_text, packing_text, metadata)
    result["extra_fields"] = {}
    result["extra_comparisons"] = []
    invoice = parse_fields(invoice_text)
    packing = parse_fields(packing_text)

    for kind, source in extras.items():
        name = DOC_NAMES[kind]
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{name} has no readable text.")
        fields = parse_fields(source)
        result["extra_fields"][kind] = fields
        if not fields:
            result["issues"].append({
                "severity": "amber", "code": "UNRECOGNISED_FORMAT", "field": kind,
                "label": name, "detail": f"Could not extract labelled fields from {name}.",
                "action": "Inspect this draft manually; scanned PDFs require OCR.",
                "invoice_value": None, "packing_value": None, "confidence": None,
            })
            result["summary"]["checks"] += 1
            continue

        for field in FIELDS[kind]:
            observed = fields.get(field)
            # A draft may legitimately omit some fields. Do not invent errors
            # for fields that are absent, or make customs/origin rulings.
            if not observed:
                continue
            baseline = invoice.get(field) or packing.get(field)
            if not baseline:
                continue
            result["summary"]["checks"] += 1
            similarity = None
            if field == "description":
                similarity, _ = description_similarity(baseline, observed)
                status = ("match" if similarity >= 0.83 else
                          "review" if similarity >= 0.48 else "mismatch")
            else:
                left, right = clean_value(field, baseline), clean_value(field, observed)
                if left is None or right is None:
                    status = "review"
                elif field in {"gross_kg", "net_kg"} and isinstance(left, Decimal) and isinstance(right, Decimal):
                    status = "match" if abs(left - right) <= Decimal("0.1") else "mismatch"
                else:
                    status = "match" if left == right else "mismatch"
            result["extra_comparisons"].append({
                "document": name, "field": field, "label": LABELS.get(field, field),
                "reference_source": "Invoice" if invoice.get(field) else "Packing list",
                "reference": baseline, "document_value": observed,
                "status": status, "similarity": round(similarity, 3) if similarity is not None else None,
            })
            if status == "match":
                result["summary"]["passed"] += 1
                continue
            severity = "red" if status == "mismatch" else "amber"
            result["issues"].append({
                "severity": severity,
                "code": "DRAFT_DOCUMENT_MISMATCH" if status == "mismatch" else "DRAFT_DOCUMENT_REVIEW",
                "field": field, "label": f"{name}: {LABELS.get(field, field)}",
                "detail": f"{name} differs from the reference document for {LABELS.get(field, field)}."
                    if status == "mismatch" else f"{name} field needs manual confirmation.",
                "action": "Compare both original documents and confirm the correct field before finalising.",
                "invoice_value": baseline, "packing_value": observed,
                "confidence": similarity,
            })
    result["summary"]["flags"] = len(result["issues"])
    result["summary"]["critical"] = sum(i["severity"] == "red" for i in result["issues"])
    result["summary"]["review"] = sum(i["severity"] == "amber" for i in result["issues"])
    result["status"] = (
        "red" if result["summary"]["critical"] else
        "amber" if result["summary"]["review"] else "green"
    )
    result["summary"]["processing_ms"] = round((perf_counter() - start) * 1000, 1)
    if extras:
        result["limitations"].append(
            "Draft bill of lading and certificate of origin: field-consistency checks only; "
            "no authenticity, HS, tariff, or rules-of-origin determination."
        )
    return result


def review_bundle_pdfs(
    invoice_bytes: bytes,
    packing_bytes: bytes,
    extras: dict[str, bytes] | None = None,
    metadata: dict | None = None,
) -> dict:
    texts = {k: extract_pdf_text(v) for k, v in (extras or {}).items()}
    return review_bundle_texts(
        extract_pdf_text(invoice_bytes), extract_pdf_text(packing_bytes), texts, metadata
    )
