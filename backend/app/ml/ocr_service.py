import asyncio
import io
import os
import threading
import time
from pathlib import Path
from typing import Any

# Ensure reliable CPU execution for PaddleX on Windows
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import numpy as np
from PIL import Image, ImageOps

from app.ml.bill_classifier import extract_bill_fields, load_config, score_bill_text
from app.ml.classifier import BillClassifier
from app.ml.extraction_service import extract_fields
from app.ml.image_preprocessing import preprocess_for_ocr, preprocess_image

_reader: Any | None = None
_reader_lock = threading.RLock()
_inference_lock = threading.Lock()
_default_classifier = BillClassifier()


class OCRServiceError(RuntimeError):
    """Raised when PaddleOCR or its local model files cannot be used."""


def _get_reader():
    """Initializes and returns the PaddleOCR singleton instance (loaded once)."""
    global _reader
    with _reader_lock:
        if _reader is None:
            config = load_config()
            ocr_cfg = config.get("ocr", {})
            lang = ocr_cfg.get("language", "en")
            use_gpu = bool(ocr_cfg.get("use_gpu", False))
            use_angle_cls = bool(ocr_cfg.get("use_angle_cls", True))

            try:
                import paddleocr
                from paddleocr import PaddleOCR
            except ImportError as error:
                raise OCRServiceError(
                    "PaddleOCR is not installed. Install backend requirements and retry."
                ) from error

            try:
                ocr_version = ocr_cfg.get("ocr_version", "PP-OCRv4")
                use_unwarping = bool(ocr_cfg.get("use_doc_unwarping", False))
                use_doc_ori = bool(ocr_cfg.get("use_doc_orientation_classify", False))
                rec_batch_size = int(ocr_cfg.get("text_recognition_batch_size", 16))

                init_kwargs: dict[str, Any] = {
                    "lang": lang,
                    "ocr_version": ocr_version,
                    "use_doc_unwarping": use_unwarping,
                    "use_doc_orientation_classify": use_doc_ori,
                    "text_recognition_batch_size": rec_batch_size,
                }
                # Check version or parameter support
                try:
                    _reader = PaddleOCR(use_textline_orientation=use_angle_cls, **init_kwargs)
                except (TypeError, ValueError):
                    try:
                        _reader = PaddleOCR(use_angle_cls=use_angle_cls, **init_kwargs)
                    except (TypeError, ValueError):
                        _reader = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang)
            except Exception as error:
                raise OCRServiceError(
                    f"PaddleOCR could not initialize its models: {error}"
                ) from error
        return _reader


def _image_array(image_bytes: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        return np.asarray(image)


def _recognize_with_reader(reader: Any, img_arr: np.ndarray) -> tuple[list[dict], float]:
    """Runs OCR inference on an RGB numpy image using the reader, handling 3.x predict, 2.x ocr, or mock readtext."""
    t_start = time.perf_counter()
    lines = []

    # 1. Mock support: if reader has readtext (for backwards test mocks)
    if hasattr(reader, "readtext"):
        raw_result = reader.readtext(img_arr, detail=1, paragraph=False)
        for box, text, confidence in raw_result:
            points = [[float(p[0]), float(p[1])] for p in box]
            lines.append(
                {
                    "text": str(text),
                    "bbox": points,
                    "confidence": max(0.0, min(1.0, float(confidence))),
                }
            )
    # 2. PaddleOCR 3.x predict() API
    elif hasattr(reader, "predict"):
        try:
            results = list(
                reader.predict(
                    img_arr,
                    use_doc_unwarping=False,
                    use_doc_orientation_classify=False,
                    use_textline_orientation=False,
                )
            )
        except TypeError:
            results = list(reader.predict(img_arr))
        for res in results:
            # 3.x dict-like result
            if isinstance(res, dict):
                rec_texts = res.get("rec_texts", [])
                rec_scores = res.get("rec_scores", [])
                rec_polys = res.get("rec_polys", [])
                for idx, text in enumerate(rec_texts):
                    score = float(rec_scores[idx]) if idx < len(rec_scores) else 0.8
                    poly = rec_polys[idx] if idx < len(rec_polys) else []
                    if hasattr(poly, "tolist"):
                        poly = poly.tolist()
                    points = [[float(p[0]), float(p[1])] for p in poly] if poly else []
                    lines.append(
                        {
                            "text": str(text),
                            "bbox": points,
                            "confidence": max(0.0, min(1.0, score)),
                        }
                    )
            # 2.x-style nested list from predict fallback
            elif isinstance(res, (list, tuple)):
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        box = item[0]
                        text_score = item[1]
                        text = str(text_score[0]) if isinstance(text_score, (list, tuple)) else str(text_score)
                        score = float(text_score[1]) if isinstance(text_score, (list, tuple)) and len(text_score) > 1 else 0.8
                        points = [[float(p[0]), float(p[1])] for p in box] if isinstance(box, (list, tuple)) else []
                        lines.append(
                            {
                                "text": text,
                                "bbox": points,
                                "confidence": max(0.0, min(1.0, score)),
                            }
                        )
    # 3. PaddleOCR 2.x ocr() API
    elif hasattr(reader, "ocr"):
        raw_result = reader.ocr(img_arr)
        if raw_result and isinstance(raw_result, list):
            page = raw_result[0] if isinstance(raw_result[0], list) else raw_result
            if page:
                for item in page:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        box = item[0]
                        text_score = item[1]
                        text = str(text_score[0]) if isinstance(text_score, (list, tuple)) else str(text_score)
                        score = float(text_score[1]) if isinstance(text_score, (list, tuple)) and len(text_score) > 1 else 0.8
                        points = [[float(p[0]), float(p[1])] for p in box] if isinstance(box, (list, tuple)) else []
                        lines.append(
                            {
                                "text": text,
                                "bbox": points,
                                "confidence": max(0.0, min(1.0, score)),
                            }
                        )

    # Sort lines reading order: top-to-bottom, left-to-right
    lines.sort(
        key=lambda l: (
            min((p[1] for p in l["bbox"]), default=0),
            min((p[0] for p in l["bbox"]), default=0),
        )
    )
    ocr_time_ms = (time.perf_counter() - t_start) * 1000
    return lines, ocr_time_ms


def _extract_sync(image_bytes: bytes) -> dict:
    started = time.perf_counter()
    config = load_config()
    max_long_side = config.get("ocr", {}).get("max_long_side", 1800)

    # 1. Load image
    t_load_start = time.perf_counter()
    img_arr_raw = _image_array(image_bytes)
    t_load_ms = (time.perf_counter() - t_load_start) * 1000

    # 2. Fast Preprocessing (RGB convert, resize longest side, light contrast enhancement)
    t_prep_start = time.perf_counter()
    img_arr_prep, prep_steps = preprocess_for_ocr(
        image_bytes,
        max_long_side=max_long_side,
        enhance_contrast=True,
    )
    preprocessing_ms = (time.perf_counter() - t_prep_start) * 1000

    # 3. PaddleOCR Singleton Inference
    with _inference_lock:
        reader = _get_reader()
        lines, ocr_time_ms = _recognize_with_reader(reader, img_arr_prep)

    # 4. Text post-processing
    t_post_start = time.perf_counter()
    full_text = "\n".join(l["text"] for l in lines)
    t_post_ms = (time.perf_counter() - t_post_start) * 1000

    # 5. Field extraction
    t_field_start = time.perf_counter()
    extraction = extract_fields(lines)
    fields = extraction.get("fields", {})
    # Augment with regex heuristic field extractor if missing
    heuristic_fields = extract_bill_fields(full_text, [l["text"] for l in lines])
    if fields.get("merchant_name", {}).get("value") is None and heuristic_fields.get("vendor_name"):
        fields["merchant_name"] = {
            "value": heuristic_fields["vendor_name"],
            "confidence": 0.75,
            "confidence_level": "medium",
            "uncertain": False,
            "reason": "Matched vendor name from top lines heuristic",
        }
    if fields.get("total_amount", {}).get("value") is None and heuristic_fields.get("total_amount") is not None:
        fields["total_amount"] = {
            "value": heuristic_fields["total_amount"],
            "confidence": 0.85,
            "confidence_level": "high",
            "uncertain": False,
            "reason": "Extracted total amount from bill keywords and patterns",
        }
    if fields.get("bill_date", {}).get("value") is None and heuristic_fields.get("bill_date"):
        fields["bill_date"] = {
            "value": heuristic_fields["bill_date"],
            "confidence": 0.8,
            "confidence_level": "high",
            "uncertain": False,
            "reason": "Extracted date pattern from bill text",
        }
    if heuristic_fields.get("bill_number"):
        fields["bill_number"] = {
            "value": heuristic_fields["bill_number"],
            "confidence": 0.8,
            "confidence_level": "high",
            "uncertain": False,
            "reason": "Matched bill/invoice number regex heuristic",
        }
    t_field_ms = (time.perf_counter() - t_field_start) * 1000

    # 6. Bill vs non-bill classification
    t_clf_start = time.perf_counter()
    # Keyword/pattern scoring
    bill_score_res = score_bill_text(full_text, config)
    # Comprehensive layout classification
    classification = _default_classifier.classify_image(image_bytes, lines, extraction=extraction)
    # Merge signals and scores
    classification["is_bill"] = bill_score_res["is_bill"]
    classification["keyword_pattern_score"] = bill_score_res["score"]
    classification["matched_signals"] = bill_score_res["matched_signals"]

    # When keyword & pattern analysis confirms a bill and image isn't non-bill (id/bank)
    if bill_score_res["is_bill"] and classification.get("document_type") not in {"identity_document", "bank_statement", "normal_photograph"}:
        if "pattern:gstin" in bill_score_res["matched_signals"] or "keyword:invoice" in bill_score_res["matched_signals"]:
            doc_type = "invoice"
        elif "keyword:receipt" in bill_score_res["matched_signals"]:
            doc_type = "receipt"
        else:
            doc_type = classification.get("document_type") if classification.get("document_type") in {"bill", "receipt", "invoice"} else "bill"
        classification["label"] = "bill"
        classification["status"] = "bill"
        classification["document_type"] = doc_type
        classification["confidence"] = max(classification.get("confidence", 0.0), bill_score_res["score"])
        classification["should_continue_ocr"] = True
        classification["should_continue_field_extraction"] = True
        classification["message"] = f"Valid {doc_type} detected with matched signals: {', '.join(bill_score_res['matched_signals'])}."
    elif not bill_score_res["is_bill"] and classification.get("label") != "bill":
        classification["should_continue_field_extraction"] = False
    t_clf_ms = (time.perf_counter() - t_clf_start) * 1000

    # Overall OCR confidence
    confidence_values = [l["confidence"] for l in lines]
    ocr_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0

    warnings = []
    warnings.extend(extraction.get("warnings", []))
    warnings.extend(classification.get("warnings", []))
    if classification.get("label") == "bill":
        for name in ("merchant_name", "bill_date", "total_amount"):
            field = fields.get(name)
            if field and field.get("uncertain"):
                warnings.append(f"Review the {name.replace('_', ' ')}; it could not be identified reliably.")

    total_time_ms = round((time.perf_counter() - started) * 1000, 2)
    timing_breakdown = {
        "image_loading_ms": round(t_load_ms, 2),
        "preprocessing_ms": round(preprocessing_ms, 2),
        "ocr_detection_recognition_ms": round(ocr_time_ms, 2),
        "text_post_processing_ms": round(t_post_ms, 2),
        "field_extraction_ms": round(t_field_ms, 2),
        "document_classification_ms": round(t_clf_ms, 2),
        "total_processing_ms": total_time_ms,
    }

    variant_info = {
        "text": full_text,
        "lines": lines,
        "fields": fields,
        "extraction_warnings": extraction.get("warnings", []),
        "classification": classification,
        "comparison_score": round(0.5 * ocr_confidence + 0.5 * min(len(full_text) / 100, 1.0), 4),
        "ocr_confidence": round(ocr_confidence, 4),
        "processing_time_ms": total_time_ms,
        "timing_breakdown": timing_breakdown,
    }

    return {
        "engine": "PaddleOCR",
        "languages": [config.get("ocr", {}).get("language", "en")],
        "text": full_text,
        "bounding_boxes": lines,
        "fields": fields,
        "classification": classification,
        "selected_variant": "preprocessed",
        "comparisons": {
            "raw": variant_info,
            "preprocessed": variant_info,
            "preprocessing_steps": prep_steps,
        },
        "warnings": list(dict.fromkeys(warnings)),
        "processing_time_ms": total_time_ms,
        "timing_breakdown": timing_breakdown,
    }


class OCRService:
    async def extract(self, image: bytes) -> dict:
        return await asyncio.to_thread(_extract_sync, image)


ocr_service = OCRService()
