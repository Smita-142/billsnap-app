import argparse
import asyncio
import csv
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

import cv2

from app.ml.ocr_service import OCRServiceError, ocr_service

EXPECTED_IMAGES = 20
EXPECTED_BILLS = 15
FIELDS = ("merchant", "date", "total", "tax")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", " ", value).strip()


def _edit_distance(reference: list[str], candidate: list[str]) -> int:
    previous = list(range(len(candidate) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(candidate, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def _error_rate(expected: str, actual: str, by_word: bool = False) -> float:
    expected_units = _normalize(expected).split() if by_word else list(_normalize(expected))
    actual_units = _normalize(actual).split() if by_word else list(_normalize(actual))
    if not expected_units:
        return 0.0 if not actual_units else 1.0
    return round(_edit_distance(expected_units, actual_units) / len(expected_units), 6)


def _exact(expected: str, actual) -> str:
    if not expected:
        return ""
    if actual is None:
        return "false"
    return str(_normalize(expected) == _normalize(str(actual))).lower()


def _field_exact(expected: str, actual, field: str) -> str:
    if not expected:
        return ""
    if field in ("total", "tax"):
        def amount(value: str) -> Decimal:
            normalized = re.sub(r"(?:₹|INR|Rs\.?|USD|EUR|GBP|US\$|€|£|,|\s)", "", value, flags=re.IGNORECASE)
            return Decimal(normalized)

        try:
            return str(actual is not None and amount(expected) == Decimal(str(actual))).lower()
        except InvalidOperation:
            return "false"
    return _exact(expected, actual)


def _validate_manifest(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_IMAGES:
        raise ValueError(f"Expected {EXPECTED_IMAGES} annotated images; found {len(rows)}.")
    if sum(row["is_bill"].strip().lower() == "true" for row in rows) != EXPECTED_BILLS:
        raise ValueError(f"Expected {EXPECTED_BILLS} bills and {EXPECTED_IMAGES - EXPECTED_BILLS} non-bills.")
    required = {"file_name", "is_bill", "expected_text", "expected_merchant", "expected_date", "expected_total", "expected_tax"}
    for index, row in enumerate(rows, start=2):
        missing = required - row.keys()
        if missing:
            raise ValueError(f"Manifest row {index} is missing columns: {', '.join(sorted(missing))}.")
        if not row["file_name"] or row["is_bill"].strip().lower() not in ("true", "false"):
            raise ValueError(f"Manifest row {index} needs a file_name and is_bill=true/false.")
        if row["is_bill"].strip().lower() == "true" and not row["expected_text"].strip():
            raise ValueError(f"Manifest row {index} needs manually verified expected_text for a bill.")


def _result_row(image_name: str, expected: dict, variant: str, result: dict | None, failure: str = "") -> dict:
    actual_fields = (result or {}).get("fields", {})
    values = {name: actual_fields.get(field, {}).get("value") for name, field in (
        ("merchant", "merchant_name"),
        ("date", "bill_date"),
        ("total", "total_amount"),
        ("tax", "tax"),
    )}
    expected_bill = expected["is_bill"].strip().lower() == "true"
    classification = (result or {}).get("classification", {}).get("label")
    classification_match = (classification == "bill") if expected_bill else (classification == "non_bill")
    reasons = [failure] if failure else []
    if not failure:
        for field in FIELDS:
            expected_value = expected.get(f"expected_{field}", "").strip()
            if expected_value and _field_exact(expected_value, values[field], field) == "false":
                reasons.append(f"{field}_mismatch")
        if not classification_match:
            reasons.append("classification_mismatch")
    extracted_text = (result or {}).get("text", "")
    return {
        "file_name": image_name,
        "variant": variant,
        "is_bill_expected": str(expected_bill).lower(),
        "expected_text": expected.get("expected_text", ""),
        "extracted_text": extracted_text,
        "cer": _error_rate(expected.get("expected_text", ""), extracted_text),
        "wer": _error_rate(expected.get("expected_text", ""), extracted_text, by_word=True),
        "expected_merchant": expected.get("expected_merchant", ""),
        "merchant_exact_match": _field_exact(expected.get("expected_merchant", "").strip(), values["merchant"], "merchant"),
        "expected_date": expected.get("expected_date", ""),
        "date_exact_match": _field_exact(expected.get("expected_date", "").strip(), values["date"], "date"),
        "expected_total": expected.get("expected_total", ""),
        "total_exact_match": _field_exact(expected.get("expected_total", "").strip(), values["total"], "total"),
        "expected_tax": expected.get("expected_tax", ""),
        "tax_exact_match": _field_exact(expected.get("expected_tax", "").strip(), values["tax"], "tax"),
        "classification": classification or "error",
        "classification_exact_match": str(classification_match).lower() if result else "false",
        "processing_time_ms": (result or {}).get("processing_time_ms", 0),
        "failure_reason": ";".join(reasons),
    }


async def evaluate(manifest: Path, image_dir: Path, output: Path) -> int:
    with manifest.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    _validate_manifest(rows)
    results = []
    image_root = image_dir.resolve()
    for expected in rows:
        image_path = (image_dir / expected["file_name"]).resolve()
        if not image_path.is_relative_to(image_root):
            raise ValueError(f"Image path must stay inside the dataset directory: {expected['file_name']}")
        if not image_path.is_file():
            raise FileNotFoundError(f"Benchmark image is missing: {image_path}")
        try:
            response = await ocr_service.extract(image_path.read_bytes())
            for variant in ("raw", "preprocessed"):
                variant_result = response["comparisons"][variant]
                variant_result["processing_time_ms"] = response["comparisons"][variant]["processing_time_ms"]
                results.append(_result_row(expected["file_name"], expected, variant, variant_result))
        except (OCRServiceError, OSError, ValueError, cv2.error) as error:
            for variant in ("raw", "preprocessed"):
                results.append(_result_row(expected["file_name"], expected, variant, None, type(error).__name__))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    completed = sum(row["classification"] != "error" for row in results)
    print(f"Wrote {len(results)} variant results for {len(rows)} images to {output} ({completed} OCR runs completed).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare raw and preprocessed EasyOCR results on a labeled receipt set.")
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/ocr/manifest.csv"))
    parser.add_argument("--images", type=Path, default=Path("benchmarks/ocr/images"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/ocr/results.csv"))
    arguments = parser.parse_args()
    try:
        return asyncio.run(evaluate(arguments.manifest, arguments.images, arguments.output))
    except (OSError, ValueError) as error:
        print(f"OCR benchmark not run: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
