import io
import re
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.ml.extraction_service import extract_fields

_SETTLEMENT_LABELS = (
    "grand total",
    "amount payable",
    "total payable",
    "payable amount",
    "amount paid",
    "balance due",
    "net amount",
    "total amount",
    "total due",
    "net total",
    "bill total",
    "invoice total",
    "order total",
    "total:",
    "total :",
    "कुल राशि",
    "कुल भुगतान",
    "देय राशि",
    "एकूण रक्कम",
    "एकूण देय",
    "देयक रक्कम",
    "toplam",
    "toplam tutar",
    "tutar",
)
_TAX_LABELS = ("gst", "cgst", "sgst", "igst", "tax", "जीएसटी", "कर", "kdv")
_PAYMENT_LABELS = ("payment", "paid by", "cash", "card", "upi", "credit", "debit", "tender", "भुगतान", "online")
_INVOICE_LABELS = ("invoice", "receipt", "bill no", "invoice no", "tax invoice", "bill of supply", "fatura", "पावती", "देयक")
_TIME_PATTERN = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[ap]\.?m\.?)?(?!\d)", re.IGNORECASE)
_MONEY_PATTERN = re.compile(r"(?:₹|INR|Rs\.?|USD|EUR|GBP|US\$|€|£)?\s*\d[\d,]*(?:\.\d{1,2})?", re.IGNORECASE)
_MENU_TERMS = (
    "menu",
    "breakfast",
    "lunch",
    "dinner",
    "appetizer",
    "appetizers",
    "starter",
    "starters",
    "dessert",
    "beverage",
    "beverages",
    "drinks",
    "per plate",
    "per person",
    "à la carte",
    "a la carte",
    "specials",
)
_IDENTITY_TERMS = (
    "identity card",
    "aadhaar",
    "aadhar",
    "passport",
    "driving licence",
    "driver license",
    "voter id",
    "voter identity",
    "date of birth",
    "national id",
    "government of india",
)
_SCREENSHOT_TERMS = (
    "screenshot",
    "battery",
    "wifi",
    "search address",
    "address bar",
    "browser",
    "http://",
    "https://",
    "www.",
    "share edit",
    "notifications",
)
_UTILITY_TERMS = (
    "electricity bill",
    "electric bill",
    "power bill",
    "water bill",
    "gas bill",
    "utility bill",
    "meter reading",
    "units consumed",
    "kwh",
    "service number",
    "consumer number",
    "consumer no",
    "किलोवाट",
    "वीज बिल",
    "वीज पुरवठा",
    "महावितरण",
    "msedcl",
    "bill of supply",
    "ग्राहक क्रमांक",
)
_GENERIC_LINES = {
    "receipt",
    "invoice",
    "tax invoice",
    "cash memo",
    "bill",
    "customer copy",
    "original",
    "duplicate",
    "date",
    "time",
    "thank you",
    "धन्यवाद",
    "पावती",
    "total",
    "grand total",
}


def _contains_term(text: str, terms: tuple[str, ...]) -> list[str]:
    matches = []
    for term in terms:
        if term.isascii():
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
                matches.append(term)
        elif term in text:
            matches.append(term)
    return matches


def _image_features(image: bytes) -> dict[str, Any]:
    with Image.open(io.BytesIO(image)) as source:
        rgb = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / max(height, 1), 3),
        "brightness": round(float(gray.mean()), 1),
        "edge_density": round(float(np.count_nonzero(edges)) / edges.size, 4),
        "color_spread": round(float(np.mean(np.std(rgb.astype(np.float32), axis=(0, 1)))), 1),
    }


def _line_bbox(line: dict, width: int, height: int) -> tuple[float, float, float, float] | None:
    box = line.get("bbox")
    if not isinstance(box, (tuple, list)) or not box:
        return None
    try:
        if isinstance(box[0], (tuple, list)):
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
        elif len(box) == 4:
            left, top, right, bottom = (float(value) for value in box)
            xs, ys = [left, right], [top, bottom]
        else:
            return None
        return min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def _normalized_lines(lines: list[dict], image: dict) -> list[dict]:
    result = []
    for line in lines:
        text = re.sub(r"\s+", " ", str(line.get("text", ""))).strip()
        if not text:
            continue
        bounds = _line_bbox(line, image["width"], image["height"])
        result.append({"text": text, "normalized_bbox": bounds})
    return result


def _merchant_evidence(lines: list[dict]) -> dict | None:
    for line in lines:
        text = line["text"]
        normalized = text.casefold().strip(" :-|")
        if not 2 <= len(text) <= 80 or normalized in _GENERIC_LINES:
            continue
        if any(term in normalized for term in _MENU_TERMS + _IDENTITY_TERMS):
            continue
        if re.search(r"\b(?:date|time|phone|mobile|tel|gstin|invoice|receipt|total|page)\b", normalized):
            continue
        if len(re.findall(r"\d", text)) > max(3, len(text) // 3):
            continue
        bounds = line["normalized_bbox"]
        return {
            "found": True,
            "text": text[:80],
            "near_top": bounds is None or bounds[1] <= 0.4,
        }
    return None


def _item_rows(lines: list[dict]) -> list[str]:
    rows = []
    for line in lines:
        text = line["text"]
        lowered = text.casefold()
        if any(term in lowered for term in _MENU_TERMS):
            continue
        if _contains_term(lowered, _SETTLEMENT_LABELS + _TAX_LABELS + _PAYMENT_LABELS + _INVOICE_LABELS):
            continue
        if re.search(r"\b(?:date|time|phone|mobile|gstin|subtotal|discount|thank you)\b", lowered):
            continue
        amount_matches = list(_MONEY_PATTERN.finditer(text))
        if not amount_matches:
            continue
        description = re.sub(_MONEY_PATTERN, " ", text)
        description = re.sub(r"\b(?:qty|quantity|rs|inr|usd|eur|gbp)\b", " ", description, flags=re.IGNORECASE)
        if re.search(r"[^\W\d_]{2,}", description, re.UNICODE):
            rows.append(text)
    return rows


_BANK_TERMS = (
    "account statement",
    "statement of account",
    "bank statement",
    "account number",
    "a/c no",
    "opening balance",
    "closing balance",
    "debit",
    "credit",
    "withdrawal",
    "deposit",
    "transaction date",
    "value date",
    "available balance",
    "ledger balance",
)
_INVOICE_DISTINCT_TERMS = (
    "commercial invoice",
    "proforma invoice",
    "bill to",
    "ship to",
    "buyer",
    "seller",
    "vendor",
    "client",
    "payment terms",
    "purchase order",
    "po no",
    "due date",
)


def _decision(
    label: str,
    reasons: list[str],
    warnings: list[str],
    *,
    confidence: float,
    evidence: dict,
    document_type: str | None = None,
) -> dict:
    doc_type = document_type or (
        "bill" if label == "bill" else "non_bill" if label == "non_bill" else "uncertain"
    )
    evidence["document_type"] = doc_type
    messages = {
        "bill": "Valid receipt detected.",
        "invoice": "Valid invoice detected.",
        "receipt": "Valid receipt detected.",
        "identity_document": "Identity document detected.",
        "bank_statement": "Bank statement detected.",
        "normal_photograph": "Normal photograph detected; no document structure found.",
        "general_document": "General text document detected.",
        "unknown": "Blank or unreadable image; no text detected.",
        "non_bill": "This image does not appear to be a bill.",
        "uncertain": "We could not confidently identify this image as a bill.",
    }
    message = messages.get(doc_type, messages.get(label, "Document processed."))
    return {
        "label": label,
        "status": label,
        "document_type": doc_type,
        "message": message,
        "confidence": round(confidence, 3),
        "confidence_basis": "uncalibrated rule-evidence score; not a probability",
        "reasons": reasons,
        "warnings": warnings,
        "should_continue_ocr": label == "bill" or doc_type in {"receipt", "invoice", "bank_statement"},
        "should_continue_field_extraction": label == "bill" or doc_type in {"receipt", "invoice", "bank_statement"},
        "evidence": evidence,
    }


class BillClassifier:
    """Document classifier distinguishing bills/receipts, invoices, identity docs, bank statements, photos, and general documents."""

    def classify_image(self, image: bytes, ocr_lines: list[dict], extraction: dict | None = None) -> dict:
        image_stats = _image_features(image)
        lines = _normalized_lines(ocr_lines, image_stats)
        text = "\n".join(line["text"] for line in lines).casefold()
        if extraction is None:
            extraction = extract_fields(ocr_lines)
        fields = extraction["fields"]

        identity_terms = _contains_term(text, _IDENTITY_TERMS)
        menu_terms = _contains_term(text, _MENU_TERMS)
        screenshot_terms = _contains_term(text, _SCREENSHOT_TERMS)
        utility_terms = _contains_term(text, _UTILITY_TERMS)
        settlement_terms = _contains_term(text, _SETTLEMENT_LABELS)
        bank_terms = _contains_term(text, _BANK_TERMS)
        invoice_terms = _contains_term(text, _INVOICE_DISTINCT_TERMS)
        tax_terms = _contains_term(text, _TAX_LABELS)
        payment_terms = _contains_term(text, _PAYMENT_LABELS)
        merchant = _merchant_evidence(lines)
        item_rows = _item_rows(lines)
        date_found = fields.get("bill_date", {}).get("value") is not None
        time_found = bool(_TIME_PATTERN.search(text))
        total_found = fields.get("total_amount", {}).get("value") is not None
        currency_found = fields.get("currency", {}).get("value") is not None
        amount_lines = [
            line for line in lines
            if _MONEY_PATTERN.search(line["text"]) and line["text"].strip()
        ]
        positioned_lines = [line for line in lines if line["normalized_bbox"] is not None]
        top_business = bool(merchant and merchant["near_top"])
        bottom_settlement = any(
            _contains_term(line["text"].casefold(), _SETTLEMENT_LABELS)
            and line["normalized_bbox"] is not None
            and line["normalized_bbox"][1] >= 0.45
            for line in lines
        )
        portrait_layout = image_stats["aspect_ratio"] < 0.9

        evidence = {
            "merchant_or_issuer": merchant,
            "date_found": date_found,
            "time_found": time_found,
            "item_row_count": len(item_rows),
            "item_rows": item_rows[:8],
            "settlement_labels": settlement_terms,
            "subtotal_found": fields.get("subtotal", {}).get("value") is not None,
            "tax_labels": tax_terms,
            "discount_found": fields.get("discount", {}).get("value") is not None,
            "payable_amount_found": total_found,
            "currency_found": currency_found,
            "payment_labels": payment_terms,
            "invoice_labels": invoice_terms,
            "bank_statement_terms": bank_terms,
            "menu_terms": menu_terms,
            "identity_document_terms": identity_terms,
            "screenshot_ui_terms": screenshot_terms,
            "utility_terms": utility_terms,
            "amount_line_count": len(amount_lines),
            "positioned_line_count": len(positioned_lines),
            "business_near_top": top_business,
            "settlement_near_bottom": bottom_settlement,
            "portrait_layout": portrait_layout,
            "visual": image_stats,
        }
        reasons = []
        warnings = [
            "Classification uses conservative text/layout rules; confidence is not calibrated on a validation dataset."
        ]

        # 1. Identity Document
        if identity_terms:
            reasons.append("Identity-document indicators were found.")
            return _decision("non_bill", reasons, warnings, confidence=1.0, evidence=evidence, document_type="identity_document")

        # 2. Bank Statement
        if len(bank_terms) >= 2 and not settlement_terms:
            reasons.append("Bank statement indicators and account structure detected.")
            return _decision("non_bill", reasons, warnings, confidence=0.92, evidence=evidence, document_type="bank_statement")

        # 3. Menu / Catalogue
        if menu_terms and not settlement_terms and not invoice_terms:
            reasons.append("Menu or catalogue section terms were found without a transaction settlement.")
            return _decision("non_bill", reasons, warnings, confidence=1.0, evidence=evidence, document_type="non_bill")

        # 4. Screenshot
        if screenshot_terms and len(screenshot_terms) >= 2:
            reasons.append("Multiple screenshot or browser interface indicators were found.")
            return _decision(
                "non_bill",
                reasons,
                warnings,
                confidence=min(1.0, len(screenshot_terms) / len(_SCREENSHOT_TERMS)),
                evidence=evidence,
                document_type="non_bill",
            )

        # 5. Empty text / Normal Photograph / Blank image
        if not lines:
            if image_stats["color_spread"] > 20.0:
                reasons.append("High color variation with no text lines suggests a normal photograph.")
                return _decision("uncertain", reasons, warnings, confidence=0.0, evidence=evidence, document_type="normal_photograph")
            reasons.append("No readable transaction text was found in the image.")
            return _decision("uncertain", reasons, warnings, confidence=0.0, evidence=evidence, document_type="unknown")

        has_settlement = bool(settlement_terms) and total_found
        has_transaction_detail = bool(
            date_found
            or time_found
            or tax_terms
            or payment_terms
            or invoice_terms
            or item_rows
            or utility_terms
        )
        has_issuer = bool(merchant or utility_terms)
        enough_layout = len(lines) >= 3 and (top_business or portrait_layout)
        structural_checks = {
            "settlement_and_amount": has_settlement,
            "issuer": has_issuer,
            "transaction_detail": has_transaction_detail,
            "receipt_layout": enough_layout,
        }
        evidence["structural_checks"] = structural_checks
        passed = sum(structural_checks.values())
        reasons.extend(name.replace("_", " ") for name, value in structural_checks.items() if value)

        # 6. Utility Bill
        if utility_terms and has_settlement and has_issuer and (date_found or tax_terms or invoice_terms):
            reasons.append("Utility-billing context and transaction details support a payable bill.")
            utility_checks = (has_settlement, has_issuer, date_found, bool(tax_terms or invoice_terms))
            confidence = sum(utility_checks) / len(utility_checks)
            return _decision("bill", reasons, warnings, confidence=confidence, evidence=evidence, document_type="bill")

        # 7. Commercial Invoice
        is_invoice = (
            any(t in text for t in ("commercial invoice", "proforma invoice", "bill to", "tax invoice"))
            or (len(invoice_terms) >= 1 and any(t in text for t in ("invoice no", "invoice number", "inv no")))
            or len(invoice_terms) >= 2
        )
        if is_invoice and (total_found or has_settlement):
            reasons.append("Commercial invoice markers, buyer/seller details, and transaction settlement present.")
            return _decision("bill", reasons, warnings, confidence=0.95, evidence=evidence, document_type="invoice")

        # 8. Standard Retail Bill / Receipt
        if has_settlement and has_issuer and has_transaction_detail and enough_layout:
            reasons.append("A named issuer, explicit payable amount, transaction detail, and receipt-like layout are present.")
            return _decision("bill", reasons, warnings, confidence=passed / len(structural_checks), evidence=evidence, document_type="receipt")

        if menu_terms:
            reasons.append("Menu/catalogue indicators conflict with transaction evidence.")
        if not has_settlement:
            reasons.append("No explicit payable, amount-paid, balance-due, or grand-total label was identified.")
        if not has_issuer:
            reasons.append("No merchant or utility issuer could be established.")
        if not has_transaction_detail:
            reasons.append("No transaction date, item, tax, invoice, or payment evidence was found.")
        if not enough_layout:
            reasons.append("Receipt-like business/header and document layout could not be established.")
        if passed == 0 and not menu_terms:
            doc_type = "normal_photograph" if image_stats["color_spread"] > 25 else "general_document"
            return _decision("non_bill", reasons, warnings, confidence=0.0, evidence=evidence, document_type=doc_type)

        doc_type = "general_document" if len(lines) >= 3 else "uncertain"
        return _decision(
            "uncertain", reasons, warnings, confidence=passed / len(structural_checks), evidence=evidence, document_type=doc_type
        )


    def classify_sync(self, text: str) -> dict:
        """Compatibility path for text-only callers; deliberately cannot accept a bill."""
        lines = [{"text": line, "bbox": []} for line in text.splitlines() if line.strip()]
        if not lines:
            return _decision(
                "uncertain",
                ["No readable transaction text was found."],
                ["Text-only classification cannot inspect image layout or visual content."],
                confidence=0.0,
                evidence={"line_count": 0},
            )
        return _decision(
            "uncertain",
            ["Image evidence is required before accepting a bill."],
            ["Text-only classification cannot inspect menus, identity cards, screenshots, or receipt layout."],
            confidence=0.0,
            evidence={"line_count": len(lines)},
        )

    async def classify(self, sanitized_text: str) -> dict:
        return self.classify_sync(sanitized_text)
