import asyncio
import io
import sys
import threading
import types
from decimal import Decimal

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.api.scanner import _normalize_image
from app.ml.classifier import BillClassifier
from app.ml.extraction_service import extract_fields
from app.ml.image_preprocessing import preprocess_image
from app.ml import ocr_service as ocr_module
from app.scripts.evaluate_ocr import _error_rate, _field_exact


def _ocr_lines(*texts):
    return [
        {
            "text": text,
            "bbox": [[10, index * 30], [300, index * 30], [300, index * 30 + 20], [10, index * 30 + 20]],
            "confidence": 0.94,
        }
        for index, text in enumerate(texts)
    ]


def _png(size=(500, 800), color=(255, 255, 255)):
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.text((40, 35), "Fresh Market", fill=(0, 0, 0))
    draw.text((40, 85), "Grand Total Rs. 1,250.00", fill=(0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_extracts_labeled_total_and_reconciles_tax_discount():
    extracted = extract_fields(
        _ocr_lines(
            "Fresh Market",
            "Date: 17/11/2026",
            "Subtotal ₹1,000.00",
            "CGST 9% ₹90.00",
            "SGST 9% ₹90.00",
            "Discount ₹10.00",
            "Grand Total ₹1,170.00",
            "Amount Paid ₹1,170.00",
            "Invoice No: FM-12345",
            "Phone: +91 9876543210",
        )
    )
    fields = extracted["fields"]
    assert fields["merchant_name"]["value"] == "Fresh Market"
    assert fields["bill_date"]["value"] == "2026-11-17"
    assert fields["subtotal"]["value"] == Decimal("1000.00")
    assert fields["tax"]["value"] == Decimal("180.00")
    assert fields["discount"]["value"] == Decimal("10.00")
    assert fields["total_amount"]["value"] == Decimal("1170.00")
    assert fields["invoice_number"]["value"] == "FM-12345"
    assert fields["currency"]["value"] == "INR"
    assert fields["phone_number"]["value"] == "919876543210"
    assert fields["total_amount"]["confidence_level"] == "high"
    assert not extracted["warnings"]


@pytest.mark.parametrize(
    ("merchant", "date_text", "total_text", "expected_total"),
    [
        ("होटल कमल", "दिनांक: १७/११/२०२६", "कुल राशि ₹१,२५०.००", Decimal("1250.00")),
        ("पुणे किराणा", "Date 17-11-2026", "एकूण रक्कम Rs. 1,250.00", Decimal("1250.00")),
    ],
)
def test_extracts_hindi_and_marathi_receipt_fields(merchant, date_text, total_text, expected_total):
    fields = extract_fields(_ocr_lines(merchant, date_text, total_text))["fields"]
    assert fields["merchant_name"]["value"] == merchant
    assert fields["bill_date"]["value"] == "2026-11-17"
    assert fields["total_amount"]["value"] == expected_total
    assert fields["currency"]["value"] == "INR"


def test_missing_total_and_ambiguous_date_remain_null():
    extracted = extract_fields(_ocr_lines("Corner Store", "Date: 01/02/2025", "Items 12.00"))
    assert extracted["fields"]["total_amount"]["value"] is None
    assert extracted["fields"]["bill_date"]["value"] is None
    assert "ambiguous" in extracted["fields"]["bill_date"]["reason"].lower()


@pytest.mark.parametrize("date_text", ("Date: 2026-11-17", "Date: Nov 17, 2026", "Date: 17-Nov-26"))
def test_parses_iso_and_named_month_dates(date_text):
    fields = extract_fields(_ocr_lines("Fresh Market", date_text))["fields"]
    assert fields["bill_date"]["value"] == "2026-11-17"


def test_distinguishes_multiple_labeled_amounts_on_one_line():
    fields = extract_fields(
        _ocr_lines("Fresh Market", "Date 17/11/2026", "Subtotal ₹1,000.00 Tax ₹180.00 Grand Total ₹1,180.00")
    )["fields"]
    assert fields["subtotal"]["value"] == Decimal("1000.00")
    assert fields["tax"]["value"] == Decimal("180.00")
    assert fields["total_amount"]["value"] == Decimal("1180.00")


def test_adds_gst_components_when_they_share_a_line():
    fields = extract_fields(_ocr_lines("Fresh Market", "CGST 9% ₹9.00 SGST 9% ₹9.00"))["fields"]
    assert fields["tax"]["value"] == Decimal("18.00")


def test_non_bill_classification_requires_receipt_structure():
    classifier = BillClassifier()
    identity_card = classifier.classify_image(
        _png(),
        _ocr_lines("Government of India", "Identity Card", "Name: Asha", "Date of birth: 17-11-2000"),
    )
    receipt = classifier.classify_image(
        _png(),
        _ocr_lines("Fresh Market", "Date: 17-11-2026", "Apples 2 50.00", "Grand Total Rs. 118", "Paid by UPI"),
    )
    assert identity_card["label"] == "non_bill"
    assert receipt["label"] == "bill"


def test_preprocessing_handles_small_blurry_rotated_and_dim_images_without_mutating_source():
    original = _png(size=(360, 500), color=(110, 110, 110))
    with Image.open(io.BytesIO(original)) as image:
        tilted = image.rotate(4, expand=True, fillcolor=(110, 110, 110)).filter(ImageFilter.GaussianBlur(radius=1.2))
        output = io.BytesIO()
        tilted.save(output, format="PNG")
    processed, steps = preprocess_image(output.getvalue())
    with Image.open(io.BytesIO(processed)) as image:
        assert image.mode == "L"
        assert image.width >= 360
        image.load()
    assert "orientation" in steps
    assert "resize_for_text" in steps
    assert "deskew" in steps
    assert "contrast_enhancement" in steps
    assert output.getvalue() != processed


def test_clear_receipt_preprocessing_avoids_unnecessary_thresholding():
    _, steps = preprocess_image(_png())
    assert "adaptive_threshold" not in steps
    assert "noise_reduction" not in steps


def test_preprocessing_reduces_visible_sensor_noise_selectively():
    image = Image.new("RGB", (1400, 1600), "white")
    ImageDraw.Draw(image).text((100, 100), "Fresh Market Grand Total Rs. 1,250.00", fill="black")
    with image:
        pixels = np.asarray(image).astype(np.int16)
    noise = np.random.default_rng(7).normal(0, 20, pixels.shape)
    noisy = np.clip(pixels + noise, 0, 255).astype(np.uint8)
    source = io.BytesIO()
    Image.fromarray(noisy).save(source, format="PNG")
    _, steps = preprocess_image(source.getvalue())
    assert "noise_reduction" in steps


def test_exif_orientation_is_applied_when_normalizing_upload():
    image = Image.new("RGB", (40, 20), "white")
    exif = image.getexif()
    exif[274] = 6
    source = io.BytesIO()
    image.save(source, format="JPEG", exif=exif)
    normalized, _, _ = _normalize_image(source.getvalue(), "image/jpeg")
    with Image.open(io.BytesIO(normalized)) as result:
        assert result.size == (20, 40)


def test_paddleocr_reader_is_cached_and_uses_cpu_with_configured_languages(monkeypatch):
    calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def predict(self, image):
            return []

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_module)
    monkeypatch.setattr(ocr_module, "_reader", None)
    try:
        first = ocr_module._get_reader()
        second = ocr_module._get_reader()
        assert first is second
        assert len(calls) == 1
    finally:
        monkeypatch.setattr(ocr_module, "_reader", None)


def test_paddleocr_response_has_comparable_raw_and_processed_results(monkeypatch):
    calls = []

    class Reader:
        def predict(self, image):
            calls.append(image.shape)
            return [
                {
                    "rec_texts": [
                        "Fresh Market",
                        "Date: 17-11-2026",
                        "Apples 2 50.00 100.00",
                        "GST Rs. 5.00",
                        "Grand Total Rs. 1,250.00",
                        "Paid by UPI",
                    ],
                    "rec_scores": [0.93, 0.91, 0.92, 0.90, 0.91, 0.90],
                    "rec_polys": [
                        [[10, 10], [200, 10], [200, 30], [10, 30]],
                        [[10, 70], [250, 70], [250, 95], [10, 95]],
                        [[10, 150], [250, 150], [250, 175], [10, 175]],
                        [[10, 230], [250, 230], [250, 255], [10, 255]],
                        [[10, 330], [300, 330], [300, 355], [10, 355]],
                        [[10, 400], [250, 400], [250, 425], [10, 425]],
                    ],
                }
            ]

    monkeypatch.setattr(ocr_module, "_get_reader", lambda: Reader())
    monkeypatch.setattr(ocr_module, "_reader", object())
    monkeypatch.setattr(ocr_module, "_inference_lock", threading.Lock())
    result = asyncio.run(ocr_module.OCRService().extract(_png(size=(400, 600))))
    assert result["engine"] == "PaddleOCR"
    assert result["selected_variant"] in ("raw", "preprocessed")
    assert set(result["comparisons"]) == {"raw", "preprocessed", "preprocessing_steps"}
    assert result["bounding_boxes"][0]["confidence"] == 0.93
    assert result["fields"]["total_amount"]["value"] == Decimal("1250.00")
    assert result["classification"]["label"] == "bill"
    assert result["classification"]["should_continue_field_extraction"] is True
    assert len(calls) >= 1
    assert result["processing_time_ms"] >= 0


def test_benchmark_error_rates_are_repeatable():
    assert _error_rate("Bill paid", "Bill paid") == 0
    assert _error_rate("bill paid", "bill payd", by_word=True) == 0.5
    assert _error_rate("", "extra") == 1
    assert _field_exact("₹1,250.00", Decimal("1250.00"), "total") == "true"


@pytest.mark.asyncio
async def test_ocr_api_validates_uploads_and_does_not_store_preview(client, auth_headers, monkeypatch):
    current_label = {"value": "bill"}

    def make_classification():
        label = current_label["value"]
        return {
            "label": label,
            "status": label,
            "message": {
                "bill": "Valid receipt detected.",
                "non_bill": "This image does not appear to be a bill.",
                "uncertain": "We could not confidently identify this image as a bill.",
            }[label],
            "confidence": 0.9,
            "confidence_basis": "uncalibrated rule-evidence score; not a probability",
            "reasons": ["Test classification."],
            "warnings": [],
            "should_continue_ocr": label == "bill",
            "should_continue_field_extraction": label == "bill",
            "evidence": {},
        }

    async def fake_extract(image):
        fields = {
            "total_amount": {
                "value": "125.00" if current_label["value"] == "bill" else None,
                "confidence": 0.8,
                "confidence_level": "high" if current_label["value"] == "bill" else "low",
                "uncertain": current_label["value"] != "bill",
                "reason": None,
            }
        }
        classification = make_classification()
        variant = {
            "text": "Corner Store\nGrand Total Rs. 125.00",
            "lines": [],
            "fields": fields,
            "extraction_warnings": [],
            "classification": classification,
            "comparison_score": 0.8,
            "ocr_confidence": 0.9,
            "processing_time_ms": 4.0,
        }
        return {
            "engine": "EasyOCR",
            "languages": ["en", "hi", "mr"],
            "text": "Corner Store\nGrand Total Rs. 125.00",
            "bounding_boxes": [],
            "fields": fields,
            "classification": classification,
            "selected_variant": "raw",
            "comparisons": {"raw": variant, "preprocessed": variant, "preprocessing_steps": []},
            "warnings": [],
            "processing_time_ms": 8.5,
        }

    monkeypatch.setattr("app.api.scanner.ocr_service.extract", fake_extract)
    invalid = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("receipt.png", b"not an image", "image/png")},
    )
    assert invalid.status_code == 415

    response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("receipt.png", _png(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["fields"]["total_amount"]["value"] == "125.00"
    assert response.json()["classification"]["message"] == "Valid receipt detected."

    current_label["value"] = "non_bill"
    non_bill_response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("menu.png", _png(), "image/png")},
    )
    assert non_bill_response.status_code == 422
    assert non_bill_response.json()["detail"]["code"] == "not_a_bill"
    assert non_bill_response.json()["detail"]["classification"]["status"] == "non_bill"

    current_label["value"] = "uncertain"
    uncertain_response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("uncertain.png", _png(), "image/png")},
    )
    assert uncertain_response.status_code == 200
    assert uncertain_response.json()["classification"]["message"] == "We could not confidently identify this image as a bill."
    assert uncertain_response.json()["fields"]["total_amount"]["value"] is None
    async with client._transport.app.state.test_session_factory() as session:
        from sqlalchemy import func, select

        from app.models.scanner_upload import ScannerUpload

        assert await session.scalar(select(func.count(ScannerUpload.id))) == 0


@pytest.mark.asyncio
async def test_ocr_api_rejects_oversized_upload(client, auth_headers, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.scanner.get_settings",
        lambda: SimpleNamespace(max_upload_bytes=1024, upload_rate_limit_per_minute=10),
    )
    response = await client.post(
        "/api/scanner/ocr",
        headers=auth_headers,
        files={"file": ("large.png", b"x" * 1025, "image/png")},
    )
    assert response.status_code == 413
