import io
import uuid
from decimal import Decimal
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.ml.classifier import BillClassifier
from app.ml.extraction_service import extract_fields
from app.ml.ocr_service import ocr_service
from tests.conftest import TEST_USER_ID


def _create_receipt_image(
    lines: list[str],
    transform: str = "clear",
    size: tuple[int, int] = (500, 800),
) -> bytes:
    """Generate a realistic test receipt fixture."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)

    # Draw simulated borders / layout
    draw.rectangle([10, 10, size[0] - 10, size[1] - 10], outline="gray", width=1)
    y = 30
    for line in lines:
        draw.text((25, y), line, fill="black")
        y += 35

    if transform == "blurry":
        img = img.filter(ImageFilter.GaussianBlur(radius=1.8))
    elif transform == "rotated":
        img = img.rotate(4, expand=True, fillcolor="white")
    elif transform == "shadows":
        # Add a gradient shadow
        arr = np.array(img, dtype=np.float32)
        gradient = np.linspace(0.4, 1.0, size[0])
        arr = arr * gradient[None, :, None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    elif transform == "low_contrast":
        arr = np.array(img, dtype=np.float32)
        arr = arr * 0.25 + 180  # very low contrast washed out
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    elif transform == "handwritten":
        # Simulate slight jitter in text placement
        img = Image.new("RGB", size, (250, 248, 240))
        draw = ImageDraw.Draw(img)
        y = 35
        for line in lines:
            draw.text((30 + (y % 7), y), line, fill=(20, 25, 45))
            y += 40

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _create_photo_image(theme: str = "person", size: tuple[int, int] = (600, 600)) -> bytes:
    """Generate a synthetic photograph with high color spread and natural scenery."""
    np.random.seed(42)
    if theme == "person":
        arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        arr[:, :] = [135, 180, 220]  # sky background
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        draw.ellipse([200, 150, 400, 380], fill=(210, 160, 130))  # head
        draw.rectangle([150, 380, 450, 600], fill=(40, 70, 130))  # shirt
    elif theme == "building":
        arr = np.random.randint(80, 200, (size[1], size[0], 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        draw.rectangle([100, 100, 500, 550], fill=(120, 110, 100))
        for r in range(4):
            for c in range(3):
                draw.rectangle([140 + c * 110, 130 + r * 90, 220 + c * 110, 190 + r * 90], fill=(220, 230, 255))
    elif theme == "food":
        arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        arr[:, :] = [230, 220, 205]
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        draw.ellipse([100, 100, 500, 500], fill=(255, 255, 255))  # plate
        draw.ellipse([180, 180, 420, 420], fill=(180, 60, 20))   # dish
        draw.ellipse([250, 250, 350, 350], fill=(240, 200, 40))  # garnish
    elif theme == "scenery":
        arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        arr[:300, :] = [100, 160, 240]  # sky
        arr[300:, :] = [40, 140, 40]    # grass
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        draw.polygon([(50, 300), (250, 120), (450, 300)], fill=(120, 120, 120))  # mountain
    else:  # random objects
        arr = np.random.randint(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        img = Image.fromarray(arr)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# =========================================================================
# A. RECEIPT TESTS
# =========================================================================

def test_scenario_a1_clear_printed_receipt():
    lines = [
        "DMart Supermarket",
        "Date: 15-11-2026",
        "Time: 14:30",
        "Invoice No: DM-98421",
        "Basmati Rice 5kg: Rs. 450.00",
        "Sunflower Oil 1L: Rs. 140.00",
        "Subtotal: Rs. 590.00",
        "CGST 2.5%: Rs. 14.75",
        "SGST 2.5%: Rs. 14.75",
        "Grand Total: Rs. 619.50",
        "Paid By: UPI",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 40], [400, i * 40], [400, i * 40 + 20], [20, i * 40 + 20]], "confidence": 0.95} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"
    assert res["document_type"] in {"receipt", "bill"}
    assert res["should_continue_field_extraction"] is True

    extraction = extract_fields(ocr_lines)
    assert extraction["fields"]["merchant_name"]["value"] == "DMart Supermarket"
    assert extraction["fields"]["total_amount"]["value"] == Decimal("619.50")
    assert extraction["fields"]["subtotal"]["value"] == Decimal("590.00")
    assert extraction["fields"]["bill_date"]["value"] == "2026-11-15"
    assert extraction["fields"]["payment_method"]["value"] == "UPI"


def test_scenario_a2_blurry_receipt():
    lines = [
        "Star Cafe",
        "Date: 10-10-2026",
        "Espresso: Rs. 120.00",
        "Tax: Rs. 6.00",
        "Grand Total: Rs. 126.00",
        "Paid by Card",
    ]
    ocr_lines = [{"text": l, "bbox": [[10, i * 35], [350, i * 35], [350, i * 35 + 18], [10, i * 35 + 18]], "confidence": 0.82} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "blurry")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"
    assert res["document_type"] in {"receipt", "bill"}


def test_scenario_a3_rotated_receipt():
    lines = [
        "Corner Grocers",
        "Date: 05-09-2026",
        "Milk: Rs. 30.00",
        "Bread: Rs. 25.00",
        "Grand Total: Rs. 55.00",
        "Paid Cash",
    ]
    ocr_lines = [{"text": l, "bbox": [[15, i * 35], [320, i * 35], [320, i * 35 + 18], [15, i * 35 + 18]], "confidence": 0.88} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "rotated")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"


def test_scenario_a4_receipt_with_shadows():
    lines = [
        "Highway Fast Food",
        "Date: 12-11-2026",
        "Burger Combo: Rs. 180.00",
        "Tax: Rs. 9.00",
        "Amount Payable: Rs. 189.00",
        "Payment: Cash",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 40], [380, i * 40], [380, i * 40 + 20], [20, i * 40 + 20]], "confidence": 0.85} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "shadows")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"


def test_scenario_a5_receipt_with_low_contrast():
    lines = [
        "Pharmacy Plus",
        "Date: 01-11-2026",
        "Medicines: Rs. 340.00",
        "Grand Total: Rs. 340.00",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 40], [350, i * 40], [350, i * 40 + 20], [20, i * 40 + 20]], "confidence": 0.78} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "low_contrast")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"


def test_scenario_a6_handwritten_bill():
    lines = [
        "Sharma Kirana",
        "Date: 18-11-2026",
        "Wheat 10kg: Rs. 350.00",
        "Sugar 2kg: Rs. 90.00",
        "Grand Total: Rs. 440.00",
        "Paid Cash",
    ]
    ocr_lines = [{"text": l, "bbox": [[30, i * 40], [360, i * 40], [360, i * 40 + 22], [30, i * 40 + 22]], "confidence": 0.85} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "handwritten")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"
    extraction = extract_fields(ocr_lines)
    assert extraction["fields"]["total_amount"]["value"] == Decimal("440.00")


# =========================================================================
# B. INVOICE TESTS
# =========================================================================

def test_scenario_b1_standard_invoice():
    lines = [
        "Acme Cloud Solutions Pvt Ltd",
        "Tax Invoice",
        "Invoice No: INV-2026-0042",
        "Invoice Date: 01-11-2026",
        "Due Date: 30-11-2026",
        "Bill To: Global Tech Enterprises",
        "Description: Cloud Hosting Q4",
        "Subtotal: Rs. 15,000.00",
        "IGST 18%: Rs. 2,700.00",
        "Grand Total: Rs. 17,700.00",
        "Payment Terms: Net 30",
    ]
    ocr_lines = [{"text": l, "bbox": [[25, i * 35], [450, i * 35], [450, i * 35 + 20], [25, i * 35 + 20]], "confidence": 0.94} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"
    assert res["document_type"] == "invoice"
    assert res["should_continue_field_extraction"] is True

    extraction = extract_fields(ocr_lines)
    assert extraction["fields"]["invoice_number"]["value"] == "INV-2026-0042"
    assert extraction["fields"]["total_amount"]["value"] == Decimal("17700.00")
    assert extraction["fields"]["subtotal"]["value"] == Decimal("15000.00")
    assert extraction["fields"]["due_date"]["value"] == "2026-11-30"
    assert extraction["fields"]["buyer"]["value"] == "Global Tech Enterprises"


def test_scenario_b2_invoice_with_table():
    lines = [
        "Apex Logistics",
        "Commercial Invoice",
        "Invoice No: AL-8812",
        "Date: 04-11-2026",
        "Item Qty Rate Amount",
        "Shipping 1 4000.00 4000.00",
        "Handling 2 500.00 1000.00",
        "Subtotal: Rs. 5000.00",
        "Tax: Rs. 900.00",
        "Total: Rs. 5900.00",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 35], [420, i * 35], [420, i * 35 + 18], [20, i * 35 + 18]], "confidence": 0.93} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"
    assert res["document_type"] == "invoice"


def test_scenario_b3_invoice_with_multiple_tax_fields():
    lines = [
        "Zenith Traders",
        "Tax Invoice",
        "Invoice No: ZT-1029",
        "Date: 08-11-2026",
        "Goods: Rs. 1000.00",
        "Subtotal: Rs. 1000.00",
        "CGST: Rs. 60.00",
        "SGST: Rs. 60.00",
        "Grand Total: Rs. 1120.00",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 35], [400, i * 35], [400, i * 35 + 18], [20, i * 35 + 18]], "confidence": 0.92} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    extraction = extract_fields(ocr_lines)
    assert extraction["fields"]["tax"]["value"] == Decimal("120.00")
    assert extraction["fields"]["total_amount"]["value"] == Decimal("1120.00")


def test_scenario_b4_invoice_poor_quality():
    lines = [
        "Delta Consulting",
        "Invoice",
        "Date: 11-11-2026",
        "Services: Rs. 2000.00",
        "Grand Total: Rs. 2000.00",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 35], [380, i * 35], [380, i * 35 + 18], [20, i * 35 + 18]], "confidence": 0.72} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "low_contrast")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "bill"


# =========================================================================
# C. NORMAL IMAGE TESTS
# =========================================================================

def test_scenario_c1_photo_person():
    img_bytes = _create_photo_image("person")
    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] in {"uncertain", "non_bill"}
    assert res["document_type"] == "normal_photograph"
    assert res["should_continue_field_extraction"] is False


def test_scenario_c2_photo_building():
    img_bytes = _create_photo_image("building")
    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] in {"uncertain", "non_bill"}
    assert res["document_type"] == "normal_photograph"


def test_scenario_c3_photo_food():
    img_bytes = _create_photo_image("food")
    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] in {"uncertain", "non_bill"}
    assert res["document_type"] == "normal_photograph"


def test_scenario_c4_photo_scenery():
    img_bytes = _create_photo_image("scenery")
    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] in {"uncertain", "non_bill"}
    assert res["document_type"] == "normal_photograph"


def test_scenario_c5_photo_random_objects():
    img_bytes = _create_photo_image("objects")
    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] in {"uncertain", "non_bill"}
    assert res["document_type"] == "normal_photograph"


def test_scenario_c6_screenshot_with_unrelated_text():
    lines = ["9:41", "wifi", "battery", "Search address", "https://example.com", "Share", "Edit"]
    ocr_lines = [{"text": l, "bbox": [[10, i * 30], [200, i * 30], [200, i * 30 + 15], [10, i * 30 + 15]], "confidence": 0.95} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "non_bill"


# =========================================================================
# D. OTHER DOCUMENT TESTS
# =========================================================================

def test_scenario_d1_identity_document():
    lines = [
        "Government of India",
        "Unique Identification Authority",
        "Aadhaar Card",
        "Name: Rahul Sharma",
        "DOB: 15/08/1990",
        "Gender: Male",
        "1234 5678 9012",
    ]
    ocr_lines = [{"text": l, "bbox": [[15, i * 35], [350, i * 35], [350, i * 35 + 20], [15, i * 35 + 20]], "confidence": 0.94} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "non_bill"
    assert res["document_type"] == "identity_document"
    assert res["should_continue_field_extraction"] is False


def test_scenario_d2_bank_statement():
    lines = [
        "HDFC Bank",
        "Statement of Account",
        "Account Number: 50100234567890",
        "Account Holder: Priya Patel",
        "Opening Balance: Rs. 45,000.00",
        "Closing Balance: Rs. 42,500.00",
        "Transaction Date: 12-11-2026",
        "Debit: Rs. 2,500.00",
    ]
    ocr_lines = [{"text": l, "bbox": [[20, i * 35], [420, i * 35], [420, i * 35 + 18], [20, i * 35 + 18]], "confidence": 0.93} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["document_type"] == "bank_statement"
    extraction = extract_fields(ocr_lines)
    assert extraction["fields"]["account_holder"]["value"] == "Priya Patel"
    assert extraction["fields"]["closing_balance"]["value"] == Decimal("42500.00")


def test_scenario_d3_general_text_document():
    lines = [
        "Project Proposal 2026",
        "Executive Summary",
        "This document describes the upcoming architectural guidelines.",
        "Team members are requested to review sections 3 through 5.",
        "Please provide feedback by Friday afternoon.",
    ]
    ocr_lines = [{"text": l, "bbox": [[25, i * 40], [450, i * 40], [450, i * 40 + 20], [25, i * 40 + 20]], "confidence": 0.96} for i, l in enumerate(lines)]
    img_bytes = _create_receipt_image(lines, "clear")

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, ocr_lines)
    assert res["label"] == "uncertain"
    assert res["document_type"] == "general_document"
    assert res["should_continue_field_extraction"] is False


def test_scenario_d4_blank_white_image():
    img = Image.new("RGB", (400, 600), "white")
    out = io.BytesIO()
    img.save(out, format="PNG")
    img_bytes = out.getvalue()

    clf = BillClassifier()
    res = clf.classify_image(img_bytes, [])
    assert res["label"] == "uncertain"
    assert res["document_type"] == "unknown"


@pytest.mark.asyncio
async def test_scenario_d5_corrupted_image(client, auth_headers):
    response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("corrupted.png", b"\x89PNG\r\n\x1a\ncorrupted bytes content here", "image/png")},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_scenario_d6_unsupported_file_format(client, auth_headers):
    response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("doc.pdf", b"%PDF-1.4...", "application/pdf")},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_scenario_d7_extremely_large_image(client, auth_headers, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(
        "app.api.scanner.get_settings",
        lambda: SimpleNamespace(max_upload_bytes=1024, upload_rate_limit_per_minute=10),
    )
    response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("huge.png", b"x" * 2048, "image/png")},
    )
    assert response.status_code == 413

