import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import func, select

from app.ml.classifier import BillClassifier
from app.models.bill import Bill
from app.models.scanner_upload import ScannerUpload
from tests.conftest import TEST_USER_ID


@dataclass(frozen=True)
class ClassificationCase:
    name: str
    expected: str
    lines: tuple[str, ...]
    transform: str = "plain"


def _image(transform: str = "plain") -> bytes:
    canvas = Image.new("RGB", (480, 720), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((30, 25, 450, 695), outline=(170, 170, 170), width=2)
    draw.text((50, 45), "Bill Snap classification fixture", fill="black")
    if transform == "blurry":
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=1.5))
    elif transform == "tilted":
        canvas = canvas.rotate(5, expand=True, fillcolor="white")
    elif transform == "selfie":
        pixels = np.zeros((720, 480, 3), dtype=np.uint8)
        pixels[:, :, 0] = 125
        pixels[:, :, 1] = 165
        pixels[:, :, 2] = 205
        canvas = Image.fromarray(pixels)
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((140, 180, 340, 380), fill=(195, 155, 125))
        draw.rectangle((90, 370, 390, 720), fill=(45, 80, 145))
    elif transform == "screenshot":
        draw.rectangle((0, 0, 480, 40), fill=(45, 45, 45))
        draw.text((12, 12), "9:41 wifi battery", fill="white")
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _lines(texts: tuple[str, ...]) -> list[dict]:
    result = []
    for index, text in enumerate(texts):
        y = 55 + index * 75
        result.append(
            {
                "text": text,
                "bbox": [[45, y], [430, y], [430, y + 24], [45, y + 24]],
                "confidence": 0.96,
            }
        )
    return result


CASES = (
    ClassificationCase(
        "clear receipt",
        "bill",
        ("Fresh Market", "Date: 17-11-2026", "Apples 2 50.00 100.00", "Subtotal Rs.100.00", "GST Rs.5.00", "Grand Total Rs.105.00", "Paid by UPI"),
    ),
    ClassificationCase(
        "blurry receipt",
        "bill",
        ("Fresh Market", "Date: 17-11-2026", "Apples 2 50.00 100.00", "Subtotal Rs.100.00", "GST Rs.5.00", "Grand Total Rs.105.00", "Paid by UPI"),
        "blurry",
    ),
    ClassificationCase(
        "tilted receipt",
        "bill",
        ("Fresh Market", "Date: 17-11-2026", "Milk 1 50.00 50.00", "Grand Total Rs.50.00", "Paid by cash"),
        "tilted",
    ),
    ClassificationCase(
        "electricity bill",
        "bill",
        ("City Power Board", "Electricity Bill", "Consumer Number C1234", "Due Date: 17-11-2026", "Units Consumed 120 kWh", "Tax Rs.20.00", "Amount Payable Rs.520.00"),
    ),
    ClassificationCase(
        "handwritten receipt transcription",
        "bill",
        ("Ravi Stores", "Date: 17-11-2026", "Rice 1 kg Rs.50.00", "Grand Total Rs.50.00", "Paid Cash"),
    ),
    ClassificationCase(
        "restaurant menu",
        "non_bill",
        ("The Cafe", "MENU", "Breakfast", "Idli Rs.50", "Lunch", "Thali Rs.150", "Dessert Rs.80"),
    ),
    ClassificationCase(
        "product catalogue",
        "uncertain",
        ("Home Supplies Catalogue", "Kitchen Appliances", "Mixer Rs.1200", "Fan Rs.2500", "Tax 18%"),
    ),
    ClassificationCase("selfie with no text", "uncertain", (), "selfie"),
    ClassificationCase(
        "identity card",
        "non_bill",
        ("Government of India", "Identity Card", "Name: Asha", "Date of birth: 17-11-2000", "ID Number 8392"),
    ),
    ClassificationCase(
        "phone screenshot",
        "non_bill",
        ("9:41", "wifi", "battery", "Screenshot", "Share", "Edit"),
        "screenshot",
    ),
    ClassificationCase(
        "ordinary business document",
        "uncertain",
        ("Customer Notice", "Please update your account information", "For questions contact support"),
    ),
)


def _classify(case: ClassificationCase) -> dict:
    return BillClassifier().classify_image(_image(case.transform), _lines(case.lines))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_image_classifier_distinguishes_receipts_from_negative_examples(case):
    result = _classify(case)
    assert result["label"] == case.expected, (case.name, result["reasons"], result["evidence"])
    assert result["status"] == result["label"]
    assert result["should_continue_ocr"] is (case.expected == "bill")
    assert result["should_continue_field_extraction"] is (case.expected == "bill")
    assert result["reasons"]
    assert 0 <= result["confidence"] <= 1
    assert "not a probability" in result["confidence_basis"]


def _classification_metrics():
    labels = [case.expected for case in CASES]
    predictions = [_classify(case)["label"] for case in CASES]
    # Uncertain is conservatively treated as rejected, not as a bill.
    actual_bill = [label == "bill" for label in labels]
    predicted_bill = [label == "bill" for label in predictions]
    tp = sum(actual and predicted for actual, predicted in zip(actual_bill, predicted_bill))
    fn = sum(actual and not predicted for actual, predicted in zip(actual_bill, predicted_bill))
    fp = sum(not actual and predicted for actual, predicted in zip(actual_bill, predicted_bill))
    tn = sum(not actual and not predicted for actual, predicted in zip(actual_bill, predicted_bill))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_acceptance_rate = fp / (fp + tn) if fp + tn else 0.0
    labels_3 = ("bill", "non_bill", "uncertain")
    matrix = {
        actual: {
            predicted: sum(
                expected == actual and found == predicted
                for expected, found in zip(labels, predictions)
            )
            for predicted in labels_3
        }
        for actual in labels_3
    }
    return {
        "confusion_matrix": matrix,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_acceptance_rate": false_acceptance_rate,
    }


def test_classification_confusion_metrics():
    metrics = _classification_metrics()
    print(f"Classification synthetic-fixture metrics: {metrics}")
    assert metrics["tp"] == 5
    assert metrics["fn"] == 0
    assert metrics["fp"] == 0
    assert metrics["tn"] == 6
    assert metrics["precision"] == 1
    assert metrics["recall"] == 1
    assert metrics["f1"] == 1
    assert metrics["false_acceptance_rate"] == 0


def test_menu_prices_and_generic_totals_do_not_qualify_as_settlement():
    menu = _classify(
        ClassificationCase(
            "menu with a generic total",
            "non_bill",
            ("The Cafe", "MENU", "Breakfast", "Idli Rs.50", "Total Items: 4"),
        )
    )
    assert menu["label"] == "non_bill"


def test_text_only_classification_never_accepts_a_bill():
    result = BillClassifier().classify_sync("Fresh Market\nGrand Total Rs. 105.00")
    assert result["label"] == "uncertain"
    assert result["should_continue_field_extraction"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "expected_status"),
    (("bill", 201), ("non_bill", 422), ("uncertain", 422)),
)
async def test_bill_creation_reclassifies_any_attached_image(client, auth_headers, monkeypatch, label, expected_status):
    upload_id = uuid.uuid4()
    async with client._transport.app.state.test_session_factory() as session:
        session.add(
            ScannerUpload(
                id=upload_id,
                user_id=TEST_USER_ID,
                storage_path=f"temporary/{TEST_USER_ID}/{upload_id}.png",
                mime_type="image/png",
                size_bytes=100,
                status="temporary",
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.commit()

    async def fake_download(path, max_bytes):
        assert path.endswith(f"{upload_id}.png")
        assert max_bytes > 0
        return _image()

    async def fake_extract(image):
        return {"classification": {"label": label, "reasons": ["Test fixture"]}}

    monkeypatch.setattr("app.api.bills.download_temporary_image", fake_download)
    monkeypatch.setattr("app.api.bills.ocr_service.extract", fake_extract)
    response = await client.post(
        "/api/bills/",
        headers=auth_headers,
        json={
            "merchant_name": "Fixture Store",
            "bill_date": "2026-11-06",
            "total_amount": "10.00",
            "upload_id": str(upload_id),
        },
    )
    assert response.status_code == expected_status
    async with client._transport.app.state.test_session_factory() as session:
        assert await session.scalar(select(func.count(Bill.id))) == (1 if label == "bill" else 0)
