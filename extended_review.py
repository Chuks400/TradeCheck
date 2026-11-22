"""Optional draft bill-of-lading and certificate-of-origin checks.

Advisory field consistency only: not a legal or customs decision engine.
The source documents and sample data never leave the local TradeCheck server.
"""
from __future__ import annotations

from time import perf_counter
import re
from engine import (
    LABELS, clean_value, compare_values, compile_patterns, description_similarity,
    extract_pdf_text, parse_document_date, parse_fields, review_texts,
)

DOC_NAMES = {"bol": "Draft bill of lading", "coo": "Draft certificate of origin",
             "decl": "Draft customs declaration"}
FIELDS = {
    "bol": ("invoice_number", "po_number", "consignee", "description",
            "quantity", "cartons", "gross_kg", "net_kg"),
    "coo": ("invoice_number", "consignee", "description", "origin", "quantity"),
    "decl": ("exporter", "consignee", "po_number", "hs_code", "description",
             "quantity", "cartons", "gross_kg", "net_kg", "origin",
             "total_value_usd", "currency", "terms"),
}
# A customs declaration uses Chinese column labels. Only the fields below are
# checked by this prototype; statutory units and customs release are out of scope.
DECL_PATTERNS = {
    "exporter": r"(?:境内发货人|发货人|出口企业|Exporter|Shipper)",
    "consignee": r"(?:境外收货人|收货人|Consignee|Buyer)",
    "po_number": r"(?:合同协议号|合同号|Purchase\s*Order|PO\s*(?:No\.?|Number|#))",
    "hs_code": r"(?:商品编号|税则号列|HS\s*(?:Code|Number))",
    "description": r"(?:商品名称(?:及规格型号)?|品名|Description\s*of\s*Goods)",
    "quantity": r"(?:数量及单位|成交数量|数量|Quantity)",
    "cartons": r"(?:件数|总件数|Cartons)",
    "packaging": r"(?:包装种类|包装|Packaging)",
    "gross_kg": r"(?:毛重\s*(?:（千克）|\(kg\))?|Gross\s*Weight)",
    "net_kg": r"(?:净重\s*(?:（千克）|\(kg\))?|Net\s*Weight)",
    "origin": r"(?:原产国\s*(?:（地区）|\(地区\))?|Country\s*of\s*Origin)",
    "total_value_usd": r"(?:总价|总金额|Total\s*(?:Value|Amount))",
    "currency": r"(?:币制|币种|Currency)",
    "terms": r"(?:成交方式|价格术语|贸易术语|Incoterms?|Terms\s*of\s*Delivery)",
    "declaration_date": r"(?:申报日期|Declaration\s*Date)",
    "export_date": r"(?:出口日期|Export\s*Date)",
}
DECL_COMPILED = compile_patterns(DECL_PATTERNS)
DECL_REFERENCE = {
    "exporter": ("invoice", "exporter"),
    "consignee": ("invoice", "consignee"),
    "po_number": ("invoice", "po_number"),
    "hs_code": ("invoice", "hs_code"),
    "description": ("invoice", "description"),
    "quantity": ("invoice", "quantity"),
    "currency": ("invoice", "currency"),
    "terms": ("invoice", "terms"),
    "total_value_usd": ("invoice", "total_value_usd"),
    "origin": ("invoice", "origin"),
    "cartons": ("packing", "cartons"),
    "gross_kg": ("packing", "gross_kg"),
    "net_kg": ("packing", "net_kg"),
}
# Every sample below is FICTIONAL and intentionally simple.
SYNTHETIC_EXTRAS = {
    "clean": {
        "bol": "Invoice No: INV-2026-001\nPurchase Order: PO-44881\nConsignee: Harbor Retail USA LLC (FICTIONAL)\nDescription of Goods: Cotton knitted T-shirts\nQuantity (pcs): 5000\nCartons: 100\nGross Weight (kg): 850.0\nNet Weight (kg): 800.0",
        "coo": "Invoice No: INV-2026-001\nConsignee: Harbor Retail USA LLC (FICTIONAL)\nDescription of Goods: Cotton knitted T-shirts\nCountry of Origin: China\nQuantity (pcs): 5000",
        "decl": "申报日期: 2026-11-15\n出口日期: 2026-11-20\n境内发货人: Demo Apparel Ltd (FICTIONAL)\n境外收货人: Harbor Retail USA LLC (FICTIONAL)\n合同协议号: PO-44881\n商品编号: 6109100000\n商品名称及规格型号: Cotton knitted T-shirts\n数量及单位: 5000 pcs\n件数: 100\n包装种类: 纸箱\n毛重（千克）: 850.0\n净重（千克）: 800.0\n原产国（地区）: China\n总价: 22,500.00 USD\n币制: USD\n成交方式: FOB",
    },
}
SYNTHETIC_EXTRAS["decl_hs_error"] = {
    **SYNTHETIC_EXTRAS["clean"],
    "decl": SYNTHETIC_EXTRAS["clean"]["decl"].replace("6109100000", "6205200000"),
}
SYNTHETIC_EXTRAS["decl_terms_review"] = {
    **SYNTHETIC_EXTRAS["clean"],
    "decl": SYNTHETIC_EXTRAS["clean"]["decl"].replace("成交方式: FOB", "成交方式: CIF"),
}
SYNTHETIC_EXTRAS["decl_date_error"] = {
    **SYNTHETIC_EXTRAS["clean"],
    "decl": SYNTHETIC_EXTRAS["clean"]["decl"].replace("申报日期: 2026-11-15", "申报日期: 2026-11-21"),
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


def _hs6(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits[:6] if len(digits) >= 6 else None


def _is_carton_packaging(value: str | None) -> bool:
    text = (value or "").casefold()
    return any(token in text for token in ("carton", "ctn", "纸箱", "纸盒"))


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
        raise ValueError(
            "Only draft bills of lading, certificates of origin and customs "
            "declarations are supported."
        )
    result = review_texts(invoice_text, packing_text, metadata)
    result["extra_fields"] = {}
    result["extra_comparisons"] = []
    invoice = parse_fields(invoice_text)
    packing = parse_fields(packing_text)

    for kind, source in extras.items():
        name = DOC_NAMES[kind]
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{name} has no readable text.")
        fields = parse_fields(source, DECL_COMPILED if kind == "decl" else None)
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
            if kind == "decl":
                ref_kind, ref_field = DECL_REFERENCE.get(field, ("invoice", field))
                baseline = (invoice if ref_kind == "invoice" else packing).get(ref_field)
                reference_source = "Invoice" if ref_kind == "invoice" else "Packing list"
            else:
                baseline = invoice.get(field) or packing.get(field)
                reference_source = "Invoice" if invoice.get(field) else "Packing list"
            if not baseline:
                continue
            if kind == "decl" and field == "cartons" and not _is_carton_packaging(fields.get("packaging")):
                # Carton counts only compare when the declaration says cartons.
                result["summary"]["checks"] += 1
                result["issues"].append({
                    "severity": "amber", "code": "DRAFT_DOCUMENT_REVIEW", "field": field,
                    "label": f"{name}: {LABELS.get(field, field)}",
                    "detail": "The declared packaging kind is not cartons, so the packing-list carton count was not compared.",
                    "action": "Confirm the packaging kind and the corresponding package count by hand.",
                    "invoice_value": baseline, "packing_value": observed, "confidence": None,
                })
                continue
            result["summary"]["checks"] += 1
            similarity = None
            note = None
            if field == "description":
                similarity, _ = description_similarity(baseline, observed)
                status = ("match" if similarity >= 0.83 else
                          "review" if similarity >= 0.48 else "mismatch")
            elif kind == "decl" and field == "hs_code":
                left, right = _hs6(baseline), _hs6(observed)
                if left is None or right is None:
                    status = "review"
                    note = "Fewer than six digits on one side, so the HS heading cannot be compared."
                else:
                    status = "match" if left == right else "mismatch"
            elif kind == "decl" and field == "total_value_usd":
                decl_terms = clean_value("terms", fields.get("terms") or "")
                inv_terms = clean_value("terms", invoice.get("terms") or "") if invoice.get("terms") else None
                if decl_terms and inv_terms and decl_terms != inv_terms:
                    status = "review"
                    note = (f"Declaration terms ({decl_terms}) differ from invoice terms "
                            f"({inv_terms}); the totals may cover different costs.")
                else:
                    status, _, _ = compare_values(field, baseline, observed)
            else:
                status, _, _ = compare_values(field, baseline, observed)
            result["extra_comparisons"].append({
                "document": name, "field": field, "label": LABELS.get(field, field),
                "reference_source": reference_source,
                "reference": baseline, "document_value": observed,
                "status": status, "similarity": round(similarity, 3) if similarity is not None else None,
            })
            if status == "match":
                result["summary"]["passed"] += 1
                continue
            severity = "red" if status == "mismatch" else "amber"
            if status == "mismatch":
                detail = note or f"{name} differs from the reference document for {LABELS.get(field, field)}."
            else:
                detail = note or f"{name} field needs manual confirmation."
            result["issues"].append({
                "severity": severity,
                "code": "DRAFT_DOCUMENT_MISMATCH" if status == "mismatch" else "DRAFT_DOCUMENT_REVIEW",
                "field": field, "label": f"{name}: {LABELS.get(field, field)}",
                "detail": detail,
                "action": "Compare both original documents and confirm the correct field before finalising.",
                "invoice_value": baseline, "packing_value": observed,
                "confidence": similarity,
            })

        if kind == "decl":
            raw_declared = fields.get("declaration_date")
            raw_exported = fields.get("export_date")
            if raw_declared or raw_exported:
                result["summary"]["checks"] += 1
                declared, declared_flag = parse_document_date(raw_declared)
                exported, exported_flag = parse_document_date(raw_exported)
                if "ambiguous" in (declared_flag, exported_flag):
                    result["issues"].append({
                        "severity": "amber", "code": "AMBIGUOUS_DECLARATION_DATE",
                        "field": "declaration_date",
                        "label": f"{name}: {LABELS.get('declaration_date', 'Declaration date')}",
                        "detail": "A date on the declaration could be read in more than one order and was not guessed.",
                        "action": "Confirm the declaration and export dates against the original.",
                        "invoice_value": raw_exported, "packing_value": raw_declared, "confidence": None,
                    })
                elif declared is None or exported is None:
                    result["issues"].append({
                        "severity": "amber", "code": "DECLARATION_DATE_UNREADABLE",
                        "field": "declaration_date",
                        "label": f"{name}: {LABELS.get('declaration_date', 'Declaration date')}",
                        "detail": "The declaration date or the export date could not be read.",
                        "action": "Confirm both dates by hand; the declaration must not post-date the export.",
                        "invoice_value": raw_exported, "packing_value": raw_declared, "confidence": None,
                    })
                elif declared > exported:
                    result["issues"].append({
                        "severity": "red", "code": "DECLARATION_AFTER_EXPORT",
                        "field": "declaration_date",
                        "label": f"{name}: {LABELS.get('declaration_date', 'Declaration date')}",
                        "detail": "The declaration date is later than the export date.",
                        "action": "Correct the dates; a declaration cannot be made after the goods leave.",
                        "invoice_value": raw_exported, "packing_value": raw_declared, "confidence": None,
                    })
                else:
                    result["summary"]["passed"] += 1
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
            "no authenticity, tariff classification or rules-of-origin determination."
        )
    if "decl" in extras:
        result["limitations"].append(
            "Draft customs declaration: HS codes are compared on the first six digits only; "
            "statutory units, packaging codes and customs release are out of scope."
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
