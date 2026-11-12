import os
import re
from pathlib import Path
from typing import Any
import yaml

CONFIG_PATH = Path(__file__).parent / "ocr_config.yaml"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_CURRENCY_RE = re.compile(r"(?:₹|Rs\.?|INR|\$|रु|TL|TRY|€|£)\s*\d+(?:[.,]\d+)?|\b\d+(?:[.,]\d+)?\s*(?:₹|Rs\.?|INR|\$|रु|TL|TRY|€|£)\b", re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}|\d{1,2}(?:st|nd|rd|th)?\s*[-/\.]?\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s*[-/\.]?\s*\d{2,4})\b",
    re.IGNORECASE,
)
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b", re.IGNORECASE)

_BILL_NO_RE = re.compile(
    r"(?:(?:invoice|bill|receipt|tax\s+invoice|fatura|bill\s+no|ggn)\s*(?:no\.?|num\.?|number|#)?|(?:no\.?|#))\s*[:\-]?\s*([A-Za-z0-9\-_/]+)",
    re.IGNORECASE,
)
_TOTAL_AMOUNT_RE = re.compile(
    r"(?:(?:grand\s+total|total\s+amount|net\s+amount|amount\s+payable|total\s+payable|balance\s+due|total|देयक\s*रक्कम|रक्कम|toplam\s*tutar|toplam|tutar)\s*[:\-]?\s*(?:₹|Rs\.?|INR|\$|रु|TL|TRY|€)?\s*|(?:\bTotal\b\s*[:\-]?\s*))(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_GENERIC_HEADERS = {
    "tax invoice", "invoice", "retail invoice", "cash memo", "bill", "receipt",
    "customer copy", "original", "duplicate", "welcome", "thank you", "phone", "tel", "date"
}


def score_bill_text(text: str, config: dict | None = None) -> dict[str, Any]:
    """Classifies text into bill vs non-bill using keywords and pattern scoring."""
    if config is None:
        config = load_config()

    cls_cfg = config.get("classification", {})
    threshold = float(cls_cfg.get("threshold", 0.35))
    keywords = cls_cfg.get("keywords", [
        "invoice", "bill", "receipt", "tax invoice", "total", "subtotal", "grand total",
        "gst", "cgst", "sgst", "igst", "tax", "amount", "qty", "rate", "cash", "paid",
        "due", "bill no", "invoice no"
    ])
    weights = cls_cfg.get("weights", {})
    kw_weight = float(weights.get("keyword", 1.0))
    currency_weight = float(weights.get("currency", 1.5))
    date_weight = float(weights.get("date", 1.0))
    gstin_weight = float(weights.get("gstin", 2.0))

    text_lower = text.lower()
    matched_signals = []
    points = 0.0

    # 1. Match Keywords
    matched_keywords = set()
    for kw in keywords:
        kw_clean = kw.lower().strip()
        if not kw_clean:
            continue
        pattern = rf"(?<!\w){re.escape(kw_clean)}(?!\w)" if " " not in kw_clean else re.escape(kw_clean)
        if re.search(pattern, text_lower):
            matched_keywords.add(kw_clean)
            matched_signals.append(f"keyword:{kw_clean}")
            points += kw_weight

    # 2. Match Patterns
    if _CURRENCY_RE.search(text):
        matched_signals.append("pattern:currency")
        points += currency_weight

    if _DATE_RE.search(text):
        matched_signals.append("pattern:date")
        points += date_weight

    if _GSTIN_RE.search(text):
        matched_signals.append("pattern:gstin")
        points += gstin_weight

    # Baseline required score for confidence 1.0 is ~5 points (e.g. 2 keywords + currency + date)
    confidence = round(min(1.0, points / 5.0), 3)
    is_bill = confidence >= threshold

    return {
        "is_bill": is_bill,
        "score": confidence,
        "confidence": confidence,
        "matched_signals": matched_signals,
    }


def extract_bill_fields(text: str, lines: list[str] | None = None) -> dict[str, Any]:
    """Heuristic regex field extraction for bills: vendor name, bill date, bill number, total amount."""
    if lines is None:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1. Total Amount
    total_amount = None
    for line in reversed(lines):
        match = _TOTAL_AMOUNT_RE.search(line)
        if match:
            clean_num = match.group(1).replace(",", "")
            try:
                val = float(clean_num)
                if val > 0:
                    total_amount = val
                    break
            except ValueError:
                pass

    # Fallback for total amount: look for currency + amount on lines with 'total' or adjacent lines
    if total_amount is None:
        for i, line in enumerate(lines):
            line_low = line.lower()
            if any(term in line_low for term in ("total", "amount payable", "grand total", "net total", "रक्कम", "toplam", "balance due", "tutar")):
                # Check current line, then next line, then previous line
                candidates = [line]
                if i + 1 < len(lines):
                    candidates.append(lines[i + 1])
                if i - 1 >= 0:
                    candidates.append(lines[i - 1])
                for cand in candidates:
                    money_matches = re.findall(r"(?:₹|Rs\.?|USD|EUR|\$|TL|€)?\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)", cand)
                    if money_matches:
                        for m in reversed(money_matches):
                            try:
                                val = float(m.replace(",", ""))
                                if val > 0:
                                    total_amount = val
                                    break
                            except ValueError:
                                pass
                    if total_amount is not None:
                        break
            if total_amount is not None:
                break

    # 2. Bill Date
    bill_date = None
    for line in lines:
        match = _DATE_RE.search(line)
        if match:
            bill_date = match.group(0).strip()
            break

    # 3. Bill / Invoice Number
    bill_number = None
    for line in lines:
        match = _BILL_NO_RE.search(line)
        if match:
            num = match.group(1).strip()
            # Basic validation that it's not a generic word or date
            if len(num) >= 2 and not num.lower() in ("date", "time", "cash", "total"):
                bill_number = num
                break

    # 4. Vendor / Merchant Name
    vendor_name = None
    for line in lines[:5]:
        clean = line.strip(" :-\t|#*")
        clean_lower = clean.lower()
        if len(clean) < 3 or len(clean) > 80:
            continue
        if clean_lower in _GENERIC_HEADERS:
            continue
        if any(h in clean_lower for h in ("tax invoice", "cash memo", "bill of supply", "gstin", "phone", "date:")):
            continue
        if sum(c.isdigit() for c in clean) > len(clean) // 3:
            continue
        vendor_name = clean
        break

    return {
        "vendor_name": vendor_name,
        "bill_date": bill_date,
        "bill_number": bill_number,
        "total_amount": total_amount,
    }

