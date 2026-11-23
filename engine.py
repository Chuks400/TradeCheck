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
    "invoice_date": r"(?:Invoice\s*Date\.?|Issue\s*Date|Document\s*Date)",
    "exporter": r"(?:Exporter|Shipper|Seller)",
    "consignee": r"(?:Consignee|Buyer)",
    "po_number": r"(?:Purchase\s*Order|P\s*/\s*O\s*(?:No\.?|Number|#)|PO\s*(?:No\.?|Number|#))",
    "description": r"(?:Description\s*of\s*Goods|Product\s*Description|Item\s*Description)",
    "hs_code": r"(?:HS|HTS)\s*(?:Code|Number)\.?",
    "origin": r"(?:Country\s*of\s*Origin|Origin\s*Country|Origin)",
    "quantity": r"(?:Quantity\s*(?:\(\s*(?:pcs|pieces|units)\s*\))?|Total\s*Quantity)",
    "cartons": r"(?:Cartons|Total\s*Cartons|Number\s*of\s*Cartons)",
    "gross_kg": r"(?:Gross\s*Weight\s*(?:\(\s*kg\s*\)|\s*kg)?|Gross\s*Weight)",
    "net_kg": r"(?:Net\s*Weight\s*(?:\(\s*kg\s*\)|\s*kg)?|Net\s*Weight)",
    "unit_price_usd": r"(?:Unit\s*Price\s*(?:\(\s*USD\s*\)|\s*USD)?|Unit\s*Price)",
    "total_value_usd": r"(?:Total\s*(?:Invoice\s*)?Value\s*(?:\(\s*USD\s*\)|\s*USD)?|Invoice\s*Total|Total\s*Amount)",
    "currency": r"(?:Currency|币制|币种)",
    "terms": r"(?:Incoterms?(?:\s*®?\s*\d{4})?|Terms\s*of\s*(?:Delivery|Trade)|Trade\s*Terms|成交方式|价格术语|贸易术语)",
}
COMPILED = {
    name: re.compile(r"^\s*" + expression + r"\s*[:：]\s*(.*?)\s*$", re.IGNORECASE)
    for name, expression in FIELD_PATTERNS.items()
}


def compile_patterns(patterns: dict[str, str]) -> dict[str, re.Pattern]:
    """Build a label table for a document whose labels differ (e.g. a Chinese customs declaration)."""
    return {
        name: re.compile(r"^\s*" + expression + r"\s*[:：]\s*(.*?)\s*$", re.IGNORECASE)
        for name, expression in patterns.items()
    }
REQUIRED = {
    # Gross weight is often listed on the packing list, not the commercial invoice.
    "invoice": ["invoice_number", "invoice_date", "description", "quantity", "cartons", "origin"],
    "packing": ["invoice_number", "description", "quantity", "cartons", "gross_kg", "origin"],
}
NUMERIC = {"quantity", "cartons", "gross_kg", "net_kg", "unit_price_usd", "total_value_usd"}
# Label text -> (canonical unit, factor to canonical unit). Only these three
# dimensions are converted; anything else is treated as "cannot tell".
UNIT_ALIASES = {
    "kg": ("kg", Decimal("1")), "kgs": ("kg", Decimal("1")), "kilo": ("kg", Decimal("1")),
    "kilos": ("kg", Decimal("1")), "kilogram": ("kg", Decimal("1")), "kilograms": ("kg", Decimal("1")),
    "lb": ("kg", Decimal("0.45359237")), "lbs": ("kg", Decimal("0.45359237")),
    "pound": ("kg", Decimal("0.45359237")), "pounds": ("kg", Decimal("0.45359237")),
    "pc": ("pcs", Decimal("1")), "pcs": ("pcs", Decimal("1")), "ea": ("pcs", Decimal("1")), "each": ("pcs", Decimal("1")), "piece": ("pcs", Decimal("1")),
    "pieces": ("pcs", Decimal("1")), "unit": ("pcs", Decimal("1")), "units": ("pcs", Decimal("1")),
    "set": ("pcs", Decimal("1")), "sets": ("pcs", Decimal("1")),
    "doz": ("pcs", Decimal("12")), "dz": ("pcs", Decimal("12")),
    "dozen": ("pcs", Decimal("12")), "dozens": ("pcs", Decimal("12")),
    "ctn": ("cartons", Decimal("1")), "ctns": ("cartons", Decimal("1")),
    "carton": ("cartons", Decimal("1")), "cartons": ("cartons", Decimal("1")),
}
BASE_UNITS = {"kg", "pcs", "cartons"}
LEGAL_WORDS = {"limited", "llc", "incorporated", "corporation", "company", "gmbh", "plc", "pty", "ag"}
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
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
    "currency": "Currency",
    "terms": "Delivery terms",
    "packaging": "Packaging type",
    "declaration_date": "Declaration date",
    "export_date": "Export date",
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


def parse_fields(text: str, compiled: dict | None = None) -> dict[str, str]:
    if not isinstance(text, str):
        raise ValueError("Document text is invalid.")
    patterns = COMPILED if compiled is None else compiled
    fields: dict[str, str] = {}
    for line in text[:MAX_TEXT].replace("\u00a0", " ").splitlines():
        line = line.strip()
        if not line:
            continue
        # PyMuPDF may put two printed table columns on one text line.
        # Split only at wide whitespace ahead of a recognised label.
        segments = re.split(r"\s{3,}(?=(?:Invoice\s*(?:No\.?|Number|Date\.?)|L/C\s*Number|Delivery\s*To|Payment\s*Term|Port\s*of)\s*:)", line, flags=re.I)
        for segment in segments:
            for field, pat in patterns.items():
                m = pat.match(segment)
                if m and m.group(1).strip() and field not in fields:
                    value = m.group(1).strip()
                    if field in ("po_number", "invoice_number", "origin", "hs_code"):
                        value = re.split(r"\s{3,}", value, maxsplit=1)[0].strip()
                    fields[field] = value
                    break

    return fields


_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")
_TRAILING_WORD = re.compile(r"\s*([A-Za-z]+)\.?\s*$")
_LEADING_LABEL = re.compile(r"^\s*(?:G\.?\s*W\.?|N\.?\s*W\.?|QTY)\s*[:.]?\s*", re.IGNORECASE)
_LEADING_CURRENCY = re.compile(r"^\s*(?:USD|EUR|RMB|CNY|GBP|JPY)\s+", re.IGNORECASE)
_TRAILING_CURRENCY = re.compile(r"\s*(?:USD|EUR|RMB|CNY|GBP|JPY)\.?\s*$", re.IGNORECASE)


def number(text: str | None) -> Decimal | None:
    """Read a number, tolerating common units, currency prefixes and G.W./N.W. labels."""
    if text is None:
        return None
    clean = str(text).strip().replace(",", "").replace("$", "").replace("¥", "")
    clean = _LEADING_LABEL.sub("", clean)
    clean = _LEADING_CURRENCY.sub("", clean)
    clean = _TRAILING_CURRENCY.sub("", clean)
    clean = _TRAILING_PAREN.sub("", clean)
    clean = re.sub(r"/\s*(?:EA|PC|PCS|UNIT|UNITS|KG|KGS)$", "", clean, flags=re.I)
    m = _TRAILING_WORD.search(clean)
    if m and m.group(1).lower() in UNIT_ALIASES:
        clean = clean[: m.start()]
    clean = clean.strip()
    if not clean:
        return None
    try:
        result = Decimal(clean)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


_CURRENCY_WORDS = {"usd", "eur", "rmb", "cny", "gbp", "jpy"}


def measure(text: str | None) -> tuple[Decimal | None, str | None]:
    """Return (value converted to a base unit, base unit).

    (None, None) means the number is unreadable; (value, "?") means a unit word
    was present but is not one this prototype knows how to convert.
    """
    value = number(text)
    if value is None:
        return None, None
    stripped = _TRAILING_PAREN.sub("", str(text).strip())
    for token in reversed(re.findall(r"[A-Za-z]+", stripped)):
        low = token.lower()
        if low in _CURRENCY_WORDS:
            continue
        alias = UNIT_ALIASES.get(low)
        if alias:
            unit, factor = alias
            return value * factor, unit
        return value, "?"
    return value, None


def normalize_name(value: str) -> str:
    """Fold punctuation and legal-suffix spelling variants for name comparison."""
    s = f" {str(value).casefold().replace('&', ' and ')} "
    s = re.sub(r"\bl\s*\.?\s*l\s*\.?\s*c\.?", " llc ", s)
    s = re.sub(r"\bco\s*\.", " company ", s)
    s = re.sub(r"\bltd\s*\.", " limited ", s)
    s = re.sub(r"\binc\s*\.", " incorporated ", s)
    s = re.sub(r"\bcorp\s*\.", " corporation ", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
    tokens = [t for t in s.split() if t]
    tokens = [{"ltd": "limited", "co": "company", "inc": "incorporated", "corp": "corporation"}.get(t, t)
              for t in tokens]
    return " ".join(tokens)


def split_name(value: str) -> tuple[str, str | None]:
    """Split a normalised company name into its core and its legal suffix."""
    tokens = normalize_name(value).split()
    legal = None
    core = []
    for token in tokens:
        if token in LEGAL_WORDS:
            legal = token
        else:
            core.append(token)
    return " ".join(core), legal


CONVERTING_ALIASES = {"doz", "dz", "dozen", "dozens", "lb", "lbs", "pound", "pounds"}


def _uses_converting_unit(text: str) -> bool:
    return any(t.lower() in CONVERTING_ALIASES for t in re.findall(r"[A-Za-z]+", str(text)))


def compare_values(field: str, a: str, b: str) -> tuple[str, Decimal | None, Decimal | None]:
    """Return (match|review|mismatch, normalised a, normalised b)."""
    if field in NUMERIC:
        va, ua = measure(a)
        vb, ub = measure(b)
        if va is None or vb is None:
            return "review", va, vb
        # An unrecognised unit word is valid data the rules cannot convert.
        if "?" in (ua, ub):
            return "review", va, vb
        if ua and ub and ua != ub:
            return "mismatch", va, vb
        # A missing unit is assumed to match a base unit, but never a converted
        # unit such as DOZ or LBS: 500 DOZ and 500 must not silently agree.
        if (ua and not ub and _uses_converting_unit(a)) or (ub and not ua and _uses_converting_unit(b)):
            return "review", va, vb
        unit = ua or ub
        tolerance = Decimal("0.1") if unit == "kg" or field in ("gross_kg", "net_kg") else Decimal("0")
        return ("match" if abs(va - vb) <= tolerance else "mismatch"), va, vb
    if field in ("consignee", "exporter"):
        core_a, legal_a = split_name(a)
        core_b, legal_b = split_name(b)
        if core_a == core_b:
            # Only the legal suffix differs: plausible formatting, but the entity
            # type differs, so a person should confirm rather than auto-pass.
            return ("match" if legal_a == legal_b or not legal_a or not legal_b else "review"), None, None
        ratio = SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()
        return ("review" if ratio >= 0.9 else "mismatch"), None, None
    aa, bb = clean_value(field, a), clean_value(field, b)
    if aa is None or bb is None:
        return "review", aa, bb
    return ("match" if aa == bb else "mismatch"), aa, bb


def parse_document_date(value: str | None) -> tuple[date | None, str]:
    """Accept common invoice date formats. Returns (date, ok|ambiguous|unrecognised)."""
    if not value:
        return None, "unrecognised"
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(s, fmt).date(), "ok"
        except ValueError:
            pass
    m = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))), "ok"
        except ValueError:
            return None, "unrecognised"
    m = re.fullmatch(r"(\d{1,2})[\s.\-]+([A-Za-z]{3,9})[\s.\-]+(\d{4})", s)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))), "ok"
        except ValueError:
            return None, "unrecognised"
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            day, month = second, first
        elif first <= 12 and second <= 12:
            return None, "ambiguous"
        else:
            return None, "unrecognised"
        try:
            return date(year, month, day), "ok"
        except ValueError:
            return None, "unrecognised"
    return None, "unrecognised"


def clean_value(field: str, value: str | None) -> Any:
    if value is None:
        return None
    if field in NUMERIC:
        return number(value)
    if field == "origin":
        s = re.sub(r"[^a-z]", "", value.lower())
        if s.startswith("madein"):
            s = s[len("madein"):]
        if s in ("prc", "china", "peoplesrepublicofchina", "mainlandchina"):
            return "china"
        if s in ("vn", "vietnam", "vietname"):
            return "vietnam"
        if s in ("kh", "cambodia"):
            return "cambodia"
        return s
    if field == "po_number":
        # "PO BW-4471" or "PO No. BW-4471" has a label, not a different ID.
        # Preserve real identifiers such as "PO-44881" (no separating label).
        value = re.sub(
            r"^\s*P\.?\s*O\.?(?:\s+(?:No\.?|Number))?(?:\s*[:#]\s*|\s+)",
            "", value, flags=re.IGNORECASE,
        )
        return re.sub(r"[\s\-]", "", value).upper()
    if field in ("invoice_number", "hs_code"):
        return re.sub(r"[\s\-]", "", value).upper()
    if field == "currency":
        s = re.sub(r"\s+", " ", value.strip().upper())
        return {"美元": "USD", "人民币": "CNY", "RMB": "CNY", "欧元": "EUR",
                "港币": "HKD", "日元": "JPY", "英镑": "GBP"}.get(s, s)
    if field == "terms":
        m = re.search(r"\b(FOB|CFR|CIF|FCA|CPT|CIP|DAP|DPU|DDP|EXW)\b", value.upper())
        return m.group(1) if m else re.sub(r"\s+", " ", value.casefold().strip())
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

    def issue(severity: str, code: str, field: str, detail: str, action: str, a=None, b=None,
              confidence=None, source_documents=()):
        issues.append({"severity": severity, "code": code, "field": field,
                       "label": LABELS.get(field, field), "detail": detail, "action": action,
                       "invoice_value": a, "packing_value": b, "confidence": confidence,
                       "source_documents": list(source_documents)})

    for side, flds, original in (("invoice", invoice, invoice_text), ("packing list", packing, packing_text)):
        kind = "invoice" if side == "invoice" else "packing"
        if not original.strip():
            checks += 1
            issue("red", "NO_EXTRACTABLE_TEXT", kind, f"No extractable text in the {side}. This may be a scanned PDF.",
                  "Use a selectable-text PDF or paste the document text. OCR is not in this version.",
                  source_documents=(kind,))
        for field in REQUIRED[kind]:
            checks += 1
            if not flds.get(field):
                issue("red", "MISSING_REQUIRED_FIELD", field, f"{side.title()} is missing {LABELS[field].lower()}.",
                      f"Check the original {side} or enter the missing information.",
                      source_documents=(kind,))
            else:
                passes += 1

    comparisons_to_make = ["invoice_number", "po_number", "quantity", "cartons", "gross_kg", "net_kg", "origin", "hs_code", "consignee", "exporter", "currency", "terms", "description"]
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
                      "Confirm product identity before finalising documents.", a, b, round(similarity, 3),
                      source_documents=("invoice", "packing"))
            else:
                status = "mismatch"
                issue("red", "DESCRIPTION_MISMATCH", field,
                      "Product descriptions are substantially different.",
                      "Confirm both documents describe the same goods.", a, b, round(similarity, 3),
                      source_documents=("invoice", "packing"))
        else:
            status, aa, bb = compare_values(field, a, b)
            if field in ("consignee", "exporter") and status == "review":
                issue("amber", "NAME_SUFFIX_REVIEW", field,
                      f"{LABELS[field]} differs only in legal form or spelling; a person should confirm the entity.",
                      "Confirm both documents name the same legal entity.", a, b,
                      source_documents=("invoice", "packing"))
            elif status == "review":
                issue("amber", "UNREADABLE_VALUE", field,
                      "This field could not be understood as a number or value.",
                      "Review both values manually.", a, b,
                      source_documents=("invoice", "packing"))
            elif status == "mismatch":
                issue("red", "CROSS_DOCUMENT_MISMATCH", field,
                      f"{LABELS[field]} differs between the invoice and packing list.",
                      "Verify the correct value and update the document before approval.", a, b,
                      source_documents=("invoice", "packing"))
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
                      "Check the weight values in the original document.", flds.get("gross_kg"), flds.get("net_kg"),
                      source_documents=("invoice" if side == "invoice" else "packing",))
            else:
                passes += 1
        for field in ("quantity", "cartons", "gross_kg", "net_kg"):
            if field in flds:
                checks += 1
                v = number(flds.get(field))
                if v is None:
                    # Present but unreadable: the document is not wrong, the tool
                    # is. Ask a person instead of asserting an error.
                    issue("amber", "UNREADABLE_VALUE", field,
                          f"{side.title()}: {LABELS[field].lower()} could not be read as a number.",
                          "Confirm this value on the original document.", flds.get(field), None,
                          source_documents=("invoice" if side == "invoice" else "packing",))
                elif v <= 0 or (field in ("quantity", "cartons") and v != v.to_integral_value()):
                    issue("red", "INVALID_NUMBER", field, f"{side.title()}: invalid {LABELS[field].lower()}.",
                          "Enter a positive, valid number.", flds.get(field), None,
                          source_documents=("invoice" if side == "invoice" else "packing",))
                else:
                    passes += 1

    qty, unit, total = (number(invoice.get(f)) for f in ("quantity", "unit_price_usd", "total_value_usd"))
    if all(invoice.get(f) for f in ("quantity", "unit_price_usd", "total_value_usd")):
        checks += 1
        if None in (qty, unit, total):
            # All three are printed but at least one cannot be read. Say so
            # instead of silently dropping the arithmetic check.
            issue("amber", "CHECK_SKIPPED", "total_value_usd",
                  "The invoice total could not be verified because quantity, unit price or total value could not be read as numbers.",
                  "Confirm these three values on the original invoice.", invoice.get("total_value_usd"), None,
                  source_documents=("invoice",))
        else:
            expected = qty * unit
            if abs(expected - total) > Decimal("0.02"):
                issue("red", "INVOICE_TOTAL_ERROR", "total_value_usd",
                      f"Invoice total is {total}, but quantity × unit price = {expected}.",
                      "Check the calculation or specify discounts and extra charges outside this MVP.", str(total), str(expected),
                      source_documents=("invoice",))
            else:
                passes += 1

    if "invoice_date" in invoice:
        checks += 1
        dt, state = parse_document_date(invoice["invoice_date"])
        if state == "ambiguous":
            issue("amber", "AMBIGUOUS_DATE", "invoice_date",
                  "The invoice date could not be read unambiguously (day/month order); do not guess.",
                  "Confirm the issue date with the original invoice.", invoice["invoice_date"],
                  source_documents=("invoice",))
        elif dt is None:
            issue("amber", "DATE_FORMAT", "invoice_date", "Invoice date is not in a recognised format.",
                  "Confirm the date with the original invoice.", invoice["invoice_date"],
                  source_documents=("invoice",))
        elif dt > date.today() + timedelta(days=1):
            issue("amber", "FUTURE_DATE", "invoice_date", "Invoice date is in the future.",
                  "Check the issue date.", invoice["invoice_date"],
                  source_documents=("invoice",))
        else:
            passes += 1

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
            "Unit conversion covers kg, pcs and cartons only (plus DOZ, LB and common spellings); anything else is flagged for review.",
            "PDF text layer required; image-only scanned PDFs need OCR, not yet included.",
            "No live company, carrier, customs or certificate-of-origin integration.",
            "NLP similarity is a baseline, not a trained model of customs/legal equivalence.",
        ],
    }
    return output


def review_pdfs(invoice_bytes: bytes, packing_bytes: bytes, metadata: dict | None = None) -> dict:
    return review_texts(extract_pdf_text(invoice_bytes), extract_pdf_text(packing_bytes), metadata)
