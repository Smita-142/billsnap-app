import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")
_AMOUNT_PATTERN = re.compile(
    r"(?<![\w/])(?:(?:₹|INR|Rs\.?|USD|EUR|GBP|US\$|€|£)\s*)?"
    r"(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d{1,2}))?(?![\w/])",
    re.IGNORECASE,
)
_TOTAL_LABELS = (
    "grand total",
    "total payable",
    "amount payable",
    "amount paid",
    "total due",
    "net total",
    "total",
    "कुल राशि",
    "कुल भुगतान",
    "एकूण रक्कम",
    "एकूण देय",
    "एकूण",
    "कुल",
    "योग",
)
_SUBTOTAL_LABELS = ("subtotal", "sub total", "उप-योग", "उप योग", "उप-बेरीज", "उप बेरीज")
_TAX_LABELS = ("tax", "gst", "cgst", "sgst", "igst", "कर", "जीएसटी")
_DISCOUNT_LABELS = ("discount", "savings", "छूट", "सवलत")
_AMOUNT_PAID_LABELS = ("amount paid", "paid amount", "paid", "भुगतान किया")
_GENERIC_MERCHANT_LINES = (
    "receipt",
    "invoice",
    "tax invoice",
    "cash memo",
    "bill",
    "date",
    "time",
    "receipt no",
    "invoice no",
    "customer copy",
    "धन्यवाद",
    "पावती",
)


def _normalize_digits(value: str) -> str:
    return value.translate(_DIGIT_MAP)


def _field(value, confidence: float, reason: str | None = None) -> dict:
    confidence = round(max(0.0, min(1.0, confidence)), 3)
    if value is None:
        return {
            "value": None,
            "confidence": 0.0,
            "confidence_level": "low",
            "uncertain": True,
            "reason": reason or "No reliable matching value was found.",
        }
    level = "high" if confidence >= 0.8 else "medium" if confidence >= 0.55 else "low"
    return {
        "value": value,
        "confidence": confidence,
        "confidence_level": level,
        "uncertain": confidence < 0.75,
        "reason": reason,
    }


def _line_text(line) -> str:
    if isinstance(line, dict):
        return str(line.get("text", ""))
    if isinstance(line, (tuple, list)) and len(line) >= 2:
        return str(line[-2])
    return str(line)


def _line_confidence(line) -> float:
    if isinstance(line, dict):
        try:
            return float(line.get("confidence", 0.5))
        except (TypeError, ValueError):
            return 0.5
    if isinstance(line, (tuple, list)) and len(line) >= 3:
        try:
            return float(line[-1])
        except (TypeError, ValueError):
            return 0.5
    return 0.5


def _line_positions(lines: list) -> list[float]:
    raw_positions = []
    for index, line in enumerate(lines):
        position = None
        if isinstance(line, dict):
            box = line.get("bbox")
            if box and isinstance(box[0], (list, tuple)):
                position = min(float(point[1]) for point in box)
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                position = float(box[1])
        raw_positions.append(position if position is not None else float(index))
    minimum = min(raw_positions, default=0.0)
    span = max(raw_positions, default=0.0) - minimum
    if span <= 0:
        return [index / max(len(lines) - 1, 1) for index in range(len(lines))]
    return [(position - minimum) / span for position in raw_positions]


def _find_labels(text: str, labels: tuple[str, ...]) -> list[tuple[str, int, int]]:
    found = []
    for label in labels:
        if label.isascii():
            matches = re.finditer(rf"(?<!\w){re.escape(label)}(?!\w)", text, re.IGNORECASE)
            found.extend((label, match.start(), match.end()) for match in matches)
        else:
            start = text.find(label)
            if start >= 0:
                found.append((label, start, start + len(label)))
    return found


def _amount_for_labels(text: str, labels: tuple[str, ...]) -> tuple[str | None, Decimal | None]:
    matches = _find_labels(text, labels)
    if not matches:
        return None, None
    label, _, label_end = max(matches, key=lambda item: (len(item[0]), -item[1]))
    normalized_text = _normalize_digits(text)
    amounts = [
        match
        for match in _AMOUNT_PATTERN.finditer(normalized_text)
        if not re.match(r"\s*%", normalized_text[match.end():])
    ]
    after_label = [match for match in amounts if match.start() >= label_end]
    chosen = min(after_label, key=lambda match: match.start()) if after_label else (
        max(amounts, key=lambda match: match.start()) if amounts else None
    )
    if chosen is None:
        return label, None
    try:
        amount = Decimal(chosen.group(1).replace(",", "") + (("." + chosen.group(2)) if chosen.group(2) else ""))
    except InvalidOperation:
        return label, None
    if amount > Decimal("999999999999.99"):
        return label, None
    return label, amount.quantize(Decimal("0.01"))


def _parse_date(text: str) -> tuple[date | None, bool]:
    text = _normalize_digits(text)
    labeled_date = re.search(r"(?i)(?:\bdate\b|दिनांक|तारीख)\s*[:#-]?\s*(.+)$", text)
    if labeled_date:
        text = labeled_date.group(1).strip()
    named_patterns = (
        "%d-%b-%Y",
        "%d/%b/%Y",
        "%d %b %Y",
        "%d-%b-%y",
        "%d %b %y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d-%B-%y",
        "%d %B %y",
        "%B %d, %Y",
        "%B %d, %y",
        "%b %d, %Y",
        "%b %d, %y",
    )
    for pattern in named_patterns:
        try:
            return datetime.strptime(text.strip(), pattern).date(), False
        except ValueError:
            continue
    match = re.search(r"(?<!\d)(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})(?!\d)", text)
    if not match:
        return None, False
    first, second, third = (int(value) for value in match.groups())
    if len(match.group(1)) == 4:
        year, month, day = first, second, third
    elif first > 31:
        return None, False
    elif first > 12:
        day, month, year = first, second, third
    elif second > 12:
        month, day, year = first, second, third
    else:
        return None, True
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, month, day), False
    except ValueError:
        return None, False


def _choose_merchant(lines: list) -> tuple[str | None, float]:
    for index, line in enumerate(lines[:8]):
        text = re.sub(r"\s+", " ", _line_text(line)).strip(" \t|:-")
        normalized = text.casefold()
        if len(text) < 2 or len(text) > 80 or any(label in normalized for label in _GENERIC_MERCHANT_LINES):
            continue
        if re.search(r"\b(?:date|time|phone|tel|gstin|invoice|receipt)\b", normalized):
            continue
        if len(re.findall(r"\d", text)) > max(3, len(text) // 3):
            continue
        confidence = 0.62 + min(_line_confidence(line), 1.0) * 0.2
        confidence += max(0.0, 0.08 - index * 0.015)
        return text[:200], confidence
    return None, 0.0


def _currency(lines: list[str]) -> tuple[str | None, float]:
    joined = "\n".join(lines)
    if "₹" in joined or re.search(r"\b(?:INR|Rs\.?)\b", joined, re.IGNORECASE):
        return "INR", 0.96 if "₹" in joined else 0.9
    for pattern, code in ((r"\bUSD\b|US\$", "USD"), (r"\bEUR\b|€", "EUR"), (r"\bGBP\b|£", "GBP")):
        if re.search(pattern, joined, re.IGNORECASE):
            return code, 0.94
    return None, 0.0


def _best_labeled_amount(lines: list, labels: tuple[str, ...], exclude: tuple[str, ...] = ()):
    candidates = []
    positions = _line_positions(lines)
    for index, line in enumerate(lines):
        text = _normalize_digits(_line_text(line))
        lowered = text.casefold()
        matched_label, amount = _amount_for_labels(lowered, labels)
        if matched_label is None or matched_label in exclude or amount is None:
            continue
        label_strength = len(matched_label)
        y = positions[index]
        confidence = _line_confidence(line)
        candidates.append((label_strength + y * 0.2 + confidence * 0.1, amount, confidence, index))
    if not candidates:
        return None, 0.0, None
    _, amount, confidence, index = max(candidates, key=lambda item: (item[0], item[3]))
    return amount, confidence, index




def extract_fields(ocr_lines: list[dict] | list) -> dict:
    lines = list(ocr_lines)
    positions = _line_positions(lines)
    texts = [_line_text(line) for line in lines]
    normalized_texts = [_normalize_digits(text) for text in texts]

    merchant, merchant_ocr = _choose_merchant(lines)
    merchant_field = _field(merchant, 0.64 + merchant_ocr * 0.32 if merchant else 0.0)

    date_candidates = []
    ambiguous_date = False
    for index, (line, text) in enumerate(zip(lines, normalized_texts)):
        parsed, ambiguous = _parse_date(text)
        ambiguous_date = ambiguous_date or ambiguous
        if parsed is not None:
            lowered = text.casefold()
            label_bonus = 0.12 if re.search(r"\bdate\b|दिनांक|तारीख", lowered) else 0.0
            date_candidates.append(
                (label_bonus + (1 - positions[index]) * 0.05 + _line_confidence(line) * 0.2, parsed, line)
            )
    if date_candidates:
        date_score, parsed_date, _ = max(date_candidates, key=lambda item: item[0])
        date_field = _field(parsed_date.isoformat(), 0.58 + min(date_score, 0.35))
    else:
        date_field = _field(None, 0.0, "Date is ambiguous." if ambiguous_date else "No valid date was found.")

    subtotal, subtotal_ocr, _ = _best_labeled_amount(lines, _SUBTOTAL_LABELS)
    tax, tax_ocr, _ = _best_labeled_amount(lines, _TAX_LABELS, exclude=("cgst", "sgst", "igst"))
    if tax is None:
        components = []
        for index, line in enumerate(lines):
            lowered = _normalize_digits(_line_text(line)).casefold()
            for component in ("cgst", "sgst", "igst"):
                if _find_labels(lowered, (component,)):
                    _, amount = _amount_for_labels(lowered, (component,))
                    if amount is not None:
                        components.append((amount, _line_confidence(line), index))
        if components:
            tax = sum((item[0] for item in components), Decimal("0.00")).quantize(Decimal("0.01"))
            tax_ocr = sum(item[1] for item in components) / len(components)

    discount, discount_ocr, _ = _best_labeled_amount(lines, _DISCOUNT_LABELS)
    amount_paid, paid_ocr, _ = _best_labeled_amount(lines, _AMOUNT_PAID_LABELS)

    total_candidates = []
    for index, line in enumerate(lines):
        text = _normalize_digits(_line_text(line))
        lowered = text.casefold()
        matched_label, amount = _amount_for_labels(lowered, _TOTAL_LABELS)
        if matched_label is None or amount is None:
            continue
        strong_total = matched_label in (
            "grand total",
            "total payable",
            "amount payable",
            "amount paid",
            "total due",
            "net total",
        )
        if not strong_total and (
            _find_labels(lowered, _SUBTOTAL_LABELS + _DISCOUNT_LABELS)
            or _find_labels(lowered, _TAX_LABELS)
        ):
            continue
        strength = 1.0 if strong_total else 0.7
        total_candidates.append(
            (strength + positions[index] * 0.15 + _line_confidence(line) * 0.1, amount, line)
        )
    if total_candidates:
        total_score, total, total_line = max(total_candidates, key=lambda item: item[0])
        total_ocr = _line_confidence(total_line)
        total_field = _field(total, 0.58 + min(total_score, 0.38) + total_ocr * 0.08)
    else:
        total_field = _field(None, 0.0, "No explicitly labeled grand total or amount payable was found.")

    # Receipt number (or invoice number)
    invoice = None
    invoice_confidence = 0.0
    invoice_pattern = re.compile(
        r"\b(?:invoice|receipt|bill)\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,})",
        re.IGNORECASE,
    )
    for index, text in enumerate(normalized_texts):
        match = invoice_pattern.search(text)
        if match:
            invoice = match.group(1).strip(" .:-")
            invoice_confidence = 0.65 + _line_confidence(lines[index]) * 0.3
            break

    # Time detection
    bill_time = None
    time_confidence = 0.0
    time_pattern = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*[ap]\.?m\.?)?(?!\d)", re.IGNORECASE)
    for index, text in enumerate(normalized_texts):
        t_match = time_pattern.search(text)
        if t_match:
            bill_time = t_match.group(0).strip()
            time_confidence = 0.65 + _line_confidence(lines[index]) * 0.25
            break

    # Payment method detection
    payment_method = None
    payment_confidence = 0.0
    payment_pattern = re.compile(r"\b(?:paid\s+by\s+)?(cash|upi|credit\s+card|debit\s+card|card|net\s*banking|google\s*pay|phonepe|paytm|cheque|neft|rtgs|imps)\b", re.IGNORECASE)
    for index, text in enumerate(normalized_texts):
        p_match = payment_pattern.search(text)
        if p_match:
            raw_method = p_match.group(1).title()
            if "Upi" in raw_method:
                payment_method = "UPI"
            elif "Credit" in raw_method:
                payment_method = "Credit Card"
            elif "Debit" in raw_method:
                payment_method = "Debit Card"
            else:
                payment_method = raw_method
            payment_confidence = 0.70 + _line_confidence(lines[index]) * 0.25
            break

    # Due date detection (invoices / bills)
    due_date_field_val = None
    due_date_conf = 0.0
    due_pattern = re.compile(r"(?i)\b(?:due\s*date|pay\s*by|payment\s*due)\s*[:#-]?\s*(.+)$")
    for index, text in enumerate(normalized_texts):
        d_match = due_pattern.search(text)
        if d_match:
            parsed_due, _ = _parse_date(d_match.group(1))
            if parsed_due:
                due_date_field_val = parsed_due.isoformat()
                due_date_conf = 0.75
                break

    # Buyer / Seller detection (invoices)
    buyer = None
    buyer_conf = 0.0
    buyer_pattern = re.compile(r"(?i)\b(?:bill\s*to|billed\s*to|customer|buyer|client|ship\s*to)\s*[:\-]?\s*(.+)$")
    for index, text in enumerate(texts):
        b_match = buyer_pattern.search(text)
        if b_match:
            candidate = b_match.group(1).strip(" .:-")
            if len(candidate) > 2:
                buyer = candidate
                buyer_conf = 0.70 + _line_confidence(lines[index]) * 0.2
                break

    # Account holder & balance (bank statements)
    account_holder = None
    account_holder_conf = 0.0
    holder_pattern = re.compile(r"(?i)\b(?:account\s*holder|account\s*name|name)\s*[:\-]?\s*([A-Za-z\s]{3,40})$")
    for index, text in enumerate(texts):
        h_match = holder_pattern.search(text)
        if h_match:
            account_holder = h_match.group(1).strip()
            account_holder_conf = 0.72
            break

    closing_balance = None
    balance_conf = 0.0
    balance_labels = ("closing balance", "available balance", "net balance", "balance")
    for index, line in enumerate(lines):
        lowered = _normalize_digits(_line_text(line)).casefold()
        if "opening balance" in lowered:
            continue
        matched_lbl, b_amount = _amount_for_labels(lowered, balance_labels)
        if matched_lbl and b_amount:
            closing_balance = b_amount
            balance_conf = 0.70 + _line_confidence(line) * 0.2
            break

    phone = None
    phone_confidence = 0.0
    phone_pattern = re.compile(r"(?<!\d)(?:\+?91[\s.-]?)?(?:[6-9]\d{9}|\d{3}[\s.-]\d{3}[\s.-]\d{4})(?!\d)")
    for index, text in enumerate(normalized_texts):
        if not re.search(r"\b(?:phone|mobile|tel|contact)\b|फोन|मोबाइल", text, re.IGNORECASE):
            continue
        match = phone_pattern.search(text)
        if match:
            phone = re.sub(r"\D", "", match.group(0))
            phone_confidence = 0.68 + _line_confidence(lines[index]) * 0.28
            break

    currency, currency_confidence = _currency(texts)
    fields = {
        "merchant_name": merchant_field,
        "bill_date": date_field,
        "total_amount": total_field,
        "subtotal": _field(subtotal, 0.56 + subtotal_ocr * 0.35 if subtotal is not None else 0.0),
        "tax": _field(tax, 0.56 + tax_ocr * 0.35 if tax is not None else 0.0),
        "discount": _field(discount, 0.56 + discount_ocr * 0.35 if discount is not None else 0.0),
        "amount_paid": _field(amount_paid, 0.56 + paid_ocr * 0.35 if amount_paid is not None else 0.0),
        "invoice_number": _field(invoice, invoice_confidence),
        "receipt_number": _field(invoice, invoice_confidence),
        "bill_time": _field(bill_time, time_confidence),
        "payment_method": _field(payment_method, payment_confidence),
        "due_date": _field(due_date_field_val, due_date_conf),
        "seller": merchant_field,
        "buyer": _field(buyer, buyer_conf),
        "account_holder": _field(account_holder, account_holder_conf),
        "closing_balance": _field(closing_balance, balance_conf),
        "currency": _field(currency, currency_confidence),
        "phone_number": _field(phone, phone_confidence),
    }


    warnings = []
    if subtotal is not None and tax is not None and total_field["value"] is not None:
        expected = subtotal + tax - (discount or Decimal("0.00"))
        difference = abs(expected - total_field["value"])
        if difference <= Decimal("0.02"):
            fields["total_amount"] = _field(total_field["value"], min(0.99, total_field["confidence"] + 0.08))
        else:
            fields["total_amount"] = _field(total_field["value"], max(0.35, total_field["confidence"] - 0.15))
            warnings.append("Subtotal, tax, and discount do not reconcile with the total; review the amount.")
    if fields["total_amount"]["uncertain"]:
        warnings.append("The amount is not a correctness probability; verify it before saving the bill.")

    return {"fields": fields, "warnings": warnings}
