"""TradeCheck Lab: transparent, local-first pre-issuance document review MVP.

Scope: commercial invoice vs packing list, one product line per document.
All decisions are advisory; document contents are not transmitted anywhere.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from io import BytesIO
from time import perf_counter
import re
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:  # Allows plain-text cases without external dependencies
    fitz = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT = 150_000
FIELD_PATTERNS = {
    "invoice_number": r"(?:Invoice\s*(?:No\.?|Number|#))",
    "invoice_date": r"(?:Invoice\s*Date|Issue\s*Date|Document\s*Date)",
    "exporter": r"(?:Exporter|Shipper|Seller)",
    "consignee": r"(?:Consignee|Buyer)",
    "po_number": r"(?:Purchase\s*Order|PO\s*(?:No\.?|Number|#))",
    "description": r"(?:Description\s*of\s*Goods|Product\s*Description|Item\s*Description)",
    "hs_code": r"(?:HS\s*(?:Code|Number))",
    "origin": r"(?:Country\s*of\s*Origin|Origin\s*Country|Origin)",
    "quantity": r"(?:Quantity\s*(?:\(\s*(?:pcs|pieces|units)\s*\))?|Total\s*Quantity)",
    "cartons": r"(?:Cartons|Total\s*Cartons|Number\s*of\s*Cartons)",
    "gross_kg": r"(?:Gross\s*Weight\s*(?:\(\s*kg\s*\)|\s*kg)?|Gross\s*Weight)",
    "net_kg": r"(?:Net\s*Weight\s*(?:\(\s*kg\s*\)|\s*kg)?|Net\s*Weight)",
    "unit_price_usd": r"(?:Unit\s*Price\s*(?:\(\s*USD\s*\)|\s*USD)?|Unit\s*Price)",
    "total_value_usd": r"(?:Total\s*(?:Invoice\s*)?Value\s*(?:\(\s*USD\s*\)|\s*USD)?|Invoice\s*Total|Total\s*Amount)",
}
COMPILED = {
    name: re.compile(r"^\s*" + expression + r"\s*:\s*(.*?)\s*$", re.IGNORECASE)
    for name, expression in FIELD_PATTERNS.items()
}
REQUIRED = {
    "invoice": ["invoice_number", "invoice_date", "description", "quantity", "cartons", "gross_kg", "origin"],
    "packing": ["invoice_number", "description", "quantity", "cartons", "gross_kg", "origin"],
}
NUMERIC = {"quantity", "cartons", "gross_kg", "net_kg", "unit_price_usd", "total_value_usd"}
LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Document date",
    "exporter": "Exporter",
    "consignee": "Consignee",
    "po_number": "Purchase order",
    "description": "Product description",
    "hs_code": "HS code",
    "origin": "Country of origin",
    "quantity": "Quantity (pcs)",
    "cartons": "Cartons",
    "gross_kg": "Gross weight (kg)",
    "net_kg": "Net weight (kg)",
    "unit_price_usd": "Unit price (USD)",
    "total_value_usd": "Invoice total (USD)",
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    if fitz is None:
        raise ValueError("PDF support is not installed. Run pip install -r requirements.txt")
    if len(pdf_bytes) > MAX_FILE_BYTES:
        raise ValueError("PDF is too large (maximum 8 MB per document).")
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.page_count > 10:
                raise ValueError("This prototype supports PDFs of up to 10 pages.")
            return "\n".join(page.get_text(sort=True) for page in doc)[:MAX_TEXT]
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("Cannot open this PDF. Check that it is not encrypted or damaged.") from e


def parse_fields(text: str) -> dict[str, str]:
    if not isinstance(text, str):
        raise ValueError("Document text is invalid.")
    fields: dict[str, str] = {}
    for line in text[:MAX_TEXT].replace("\u00a0", " ").splitlines():
        line = line.strip()
        if not line:
            continue
        for field, pat in COMPILED.items():
            m = pat.match(line)
            if m and m.group(1).strip() and field not in fields:
                fields[field] = m.group(1).strip()
                break
    return fields


def number(text: str | None) -> Decimal | None:
    if text is None:
        return None
    clean = str(text).strip().replace(",", "").replace("$", "").replace("¥", "")
    clean = re.sub(r"\s*(?:USD|pcs|pieces|kg|cartons)$", "", clean, flags=re.IGNORECASE).strip()
    if not clean:
        return None
    try:
        result = Decimal(clean)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def clean_value(field: str, value: str | None) -> Any:
    if value is None:
        return None
    if field in NUMERIC:
        return number(value)
    if field == "origin":
        s = re.sub(r"[^a-z]", "", value.lower())
        if s in ("prc", "china", "peoplesrepublicofchina", "mainlandchina"):
            return "china"
        if s in ("vn", "vietnam", "vietname"):
            return "vietnam"
        if s in ("kh", "cambodia"):
            return "cambodia"
        return s
    if field in ("invoice_number", "po_number", "hs_code"):
        return re.sub(r"[\s\-]", "", value).upper()
    return re.sub(r"\s+", " ", value.casefold().strip())


def description_similarity(a: str, b: str) -> tuple[float, str]:
    # Lightweight NLP baseline: character n-gram TF-IDF, not an LLM or legal judgment.
    def normalize(s: str) -> str:
        s = s.casefold().replace("t-shirts", "tshirts").replace("t shirts", "tshirts")
        s = re.sub(r"\btee\s*shirts?\b", "tshirts", s)
        s = re.sub(r"[^a-z0-9]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()
    a, b = normalize(a), normalize(b)
    if a == b:
        return 1.0, "normalised text"
    if TfidfVectorizer is not None:
        try:
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5))
            X = vec.fit_transform([a, b])
            return float(cosine_similarity(X[0:1], X[1:2])[0, 0]), "NLP TF-IDF similarity"
        except ValueError:
            pass
    return SequenceMatcher(None, a, b).ratio(), "text similarity fallback"


def review_texts(invoice_text: str, packing_text: str, metadata: dict | None = None) -> dict:
    started = perf_counter()
    invoice = parse_fields(invoice_text)
    packing = parse_fields(packing_text)
    issues: list[dict] = []
    checks = 0
    passes = 0
    comparisons = []

    def issue(severity: str, code: str, field: str, detail: str, action: str, a=None, b=None, confidence=None):
        issues.append({"severity": severity, "code": code, "field": field,
                       "label": LABELS.get(field, field), "detail": detail, "action": action,
                       "invoice_value": a, "packing_value": b, "confidence": confidence})

    for side, flds, original in (("invoice", invoice, invoice_text), ("packing list", packing, packing_text)):
        kind = "invoice" if side == "invoice" else "packing"
        if not original.strip():
            checks += 1
            issue("red", "NO_EXTRACTABLE_TEXT", kind, f"No extractable text in the {side}. This may be a scanned PDF.",
                  "Use a selectable-text PDF or paste the document text. OCR is not in this version.")
        for field in REQUIRED[kind]:
            checks += 1
            if not flds.get(field):
                issue("red", "MISSING_REQUIRED_FIELD", field, f"{side.title()} is missing {LABELS[field].lower()}.",
                      f"Check the original {side} or enter the missing information.")
            else:
                passes += 1

    comparisons_to_make = ["invoice_number", "po_number", "quantity", "cartons", "gross_kg", "net_kg", "origin", "hs_code", "consignee", "description"]
    for field in comparisons_to_make:
        a, b = invoice.get(field), packing.get(field)
        if not a or not b:
            continue
        checks += 1
        similarity = None
        method = "exact/rule"
        if field == "description":
            similarity, method = description_similarity(a, b)
            if similarity >= 0.83:
                status = "match"
            elif similarity >= 0.48:
                status = "review"
                issue("amber", "DESCRIPTION_REVIEW", field,
                      f"Descriptions may refer to the same product (NLP similarity {similarity:.0%}); a person should verify.",
                      "Confirm product identity before finalising documents.", a, b, round(similarity, 3))
            else:
                status = "mismatch"
                issue("red", "DESCRIPTION_MISMATCH", field,
                      "Product descriptions are substantially different.",
                      "Confirm both documents describe the same goods.", a, b, round(similarity, 3))
        else:
            aa, bb = clean_value(field, a), clean_value(field, b)
            if aa is None or bb is None:
                status = "review"
                issue("amber", "UNREADABLE_VALUE", field,
                      "This field could not be understood as a number or value.",
                      "Review both values manually.", a, b)
            elif field in {"gross_kg", "net_kg"}:
                status = "match" if abs(aa - bb) <= Decimal("0.1") else "mismatch"
            else:
                status = "match" if aa == bb else "mismatch"
            if status == "mismatch":
                issue("red", "CROSS_DOCUMENT_MISMATCH", field,
                      f"{LABELS[field]} differs between the invoice and packing list.",
                      "Verify the correct value and update the document before approval.", a, b)
        if status == "match":
            passes += 1
        comparisons.append({"field": field, "label": LABELS[field], "invoice": a, "packing": b,
                            "status": status, "similarity": round(similarity, 3) if similarity is not None else None,
                            "method": method})

    # Per-document rules, independent of cross-document comparison.
    for side, flds in (("invoice", invoice), ("packing list", packing)):
        g, n = number(flds.get("gross_kg")), number(flds.get("net_kg"))
        if g is not None and n is not None:
            checks += 1
            if g < n:
                issue("red", "WEIGHT_RULE", "gross_kg", f"{side.title()}: gross weight is less than net weight.",
                      "Check the weight values in the original document.", flds.get("gross_kg"), flds.get("net_kg"))
            else:
                passes += 1
        for field in ("quantity", "cartons", "gross_kg", "net_kg"):
            if field in flds:
                checks += 1
                v = number(flds.get(field))
                if v is None or v <= 0 or (field in ("quantity", "cartons") and v != v.to_integral_value()):
                    issue("red", "INVALID_NUMBER", field, f"{side.title()}: invalid {LABELS[field].lower()}.",
                          "Enter a positive, valid number.", flds.get(field), None)
                else:
                    passes += 1

    qty, unit, total = (number(invoice.get(f)) for f in ("quantity", "unit_price_usd", "total_value_usd"))
    if None not in (qty, unit, total):
        checks += 1
        expected = qty * unit
        if abs(expected - total) > Decimal("0.02"):
            issue("red", "INVOICE_TOTAL_ERROR", "total_value_usd",
                  f"Invoice total is {total}, but quantity × unit price = {expected}.",
                  "Check the calculation or specify discounts and extra charges outside this MVP.", str(total), str(expected))
        else:
            passes += 1

    if "invoice_date" in invoice:
        checks += 1
        try:
            dt = datetime.strptime(invoice["invoice_date"], "%Y-%m-%d").date()
            if dt > date.today() + timedelta(days=1):
                issue("amber", "FUTURE_DATE", "invoice_date", "Invoice date is in the future.",
                      "Check the issue date.", invoice["invoice_date"])
            else:
                passes += 1
        except ValueError:
            issue("amber", "DATE_FORMAT", "invoice_date", "Invoice date is not in YYYY-MM-DD format.",
                  "Confirm the date with the original invoice.", invoice["invoice_date"])

    # Human-friendly status: RED -> stop and investigate; AMBER -> human review; GREEN -> no detected issues.
    risk = "red" if any(i["severity"] == "red" for i in issues) else ("amber" if issues else "green")
    output = {
        "status": risk,
        "summary": {
            "checks": checks,
            "passed": passes,
            "flags": len(issues),
            "critical": sum(i["severity"] == "red" for i in issues),
            "review": sum(i["severity"] == "amber" for i in issues),
            "processing_ms": round((perf_counter() - started) * 1000, 1),
        },
        "invoice_fields": invoice,
        "packing_fields": packing,
        "comparisons": comparisons,
        "issues": issues,
        "metadata": metadata or {},
        "limitations": [
            "Prototype only: does not issue or legally approve trade documents.",
            "Supports one product line per document; multi-line invoices need further development.",
            "PDF text layer required; image-only scanned PDFs need OCR, not yet included.",
            "No live company, carrier, customs or certificate-of-origin integration.",
            "NLP similarity is a baseline, not a trained model of customs/legal equivalence.",
        ],
    }
    return output


def review_pdfs(invoice_bytes: bytes, packing_bytes: bytes, metadata: dict | None = None) -> dict:
    return review_texts(extract_pdf_text(invoice_bytes), extract_pdf_text(packing_bytes), metadata)
