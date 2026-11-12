import argparse
import csv
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Ensure reliable CPU execution for PaddleX
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import numpy as np
from PIL import Image, ImageOps

from app.ml.bill_classifier import extract_bill_fields, load_config, score_bill_text
from app.ml.image_preprocessing import preprocess_for_ocr

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_ocr")

# Process-local model instance (each worker loads its own instance once)
_WORKER_OCR: Any | None = None


def init_worker(config: dict | None = None) -> None:
    """Worker process initializer: loads its own dedicated PaddleOCR instance."""
    global _WORKER_OCR
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    if config is None:
        config = load_config()

    ocr_cfg = config.get("ocr", {})
    lang = ocr_cfg.get("language", "en")
    use_angle_cls = bool(ocr_cfg.get("use_angle_cls", False))
    ocr_version = ocr_cfg.get("ocr_version", "PP-OCRv4")
    use_unwarping = bool(ocr_cfg.get("use_doc_unwarping", False))
    use_doc_ori = bool(ocr_cfg.get("use_doc_orientation_classify", False))
    rec_batch_size = int(ocr_cfg.get("text_recognition_batch_size", 16))

    from paddleocr import PaddleOCR

    init_kwargs = {
        "lang": lang,
        "ocr_version": ocr_version,
        "use_doc_unwarping": use_unwarping,
        "use_doc_orientation_classify": use_doc_ori,
        "text_recognition_batch_size": rec_batch_size,
    }

    try:
        _WORKER_OCR = PaddleOCR(use_textline_orientation=use_angle_cls, **init_kwargs)
    except (TypeError, ValueError):
        try:
            _WORKER_OCR = PaddleOCR(use_angle_cls=use_angle_cls, **init_kwargs)
        except (TypeError, ValueError):
            _WORKER_OCR = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang)

    logger.info("Worker process %d initialized dedicated PaddleOCR model instance", os.getpid())


def _extract_lines_from_result(pred_results: list) -> list[str]:
    lines = []
    for res in pred_results:
        if isinstance(res, dict):
            rec_texts = res.get("rec_texts", [])
            for t in rec_texts:
                if str(t).strip():
                    lines.append(str(t).strip())
        elif isinstance(res, (list, tuple)):
            for item in res:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_score = item[1]
                    text = str(text_score[0]) if isinstance(text_score, (list, tuple)) else str(text_score)
                    if text.strip():
                        lines.append(text.strip())
    return lines


def process_single_image(image_path: str | Path, config: dict | None = None) -> dict[str, Any]:
    """Processes a single image file through preprocessing, OCR, classification, and field extraction."""
    global _WORKER_OCR
    started = time.perf_counter()
    image_path = Path(image_path)
    file_str = str(image_path.resolve())

    if config is None:
        config = load_config()

    max_long_side = config.get("ocr", {}).get("max_long_side", 1800)

    # 1. Graceful error handling for reading / decoding image
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        if not image_bytes:
            raise ValueError("Empty image file")
        img_arr, _ = preprocess_for_ocr(image_bytes, max_long_side=max_long_side, enhance_contrast=True)
    except Exception as err:
        elapsed = round(time.perf_counter() - started, 3)
        logger.error("Failed to load or preprocess %s: %s", image_path.name, err)
        return {
            "file": file_str,
            "is_bill": False,
            "score": 0.0,
            "matched_signals": [],
            "fields": None,
            "text": "",
            "error": str(err),
            "processing_time_sec": elapsed,
        }

    # 2. OCR Inference
    try:
        if _WORKER_OCR is None:
            init_worker(config)
        ocr_model = _WORKER_OCR

        try:
            pred_results = list(
                ocr_model.predict(
                    img_arr,
                    use_doc_unwarping=False,
                    use_doc_orientation_classify=False,
                    use_textline_orientation=False,
                )
            ) if hasattr(ocr_model, "predict") else list(ocr_model.ocr(img_arr))
        except TypeError:
            pred_results = list(ocr_model.predict(img_arr)) if hasattr(ocr_model, "predict") else list(ocr_model.ocr(img_arr))
        lines = _extract_lines_from_result(pred_results)
        full_text = "\n".join(lines)
    except Exception as err:
        elapsed = round(time.perf_counter() - started, 3)
        logger.error("OCR inference failed for %s: %s", image_path.name, err)
        return {
            "file": file_str,
            "is_bill": False,
            "score": 0.0,
            "matched_signals": [],
            "fields": None,
            "text": "",
            "error": str(err),
            "processing_time_sec": elapsed,
        }

    # 3. Bill vs Non-bill Classification
    classification = score_bill_text(full_text, config)
    is_bill = classification["is_bill"]
    score = classification["score"]
    matched_signals = classification["matched_signals"]

    # 4. Field Extraction (for bills only)
    if is_bill:
        fields = extract_bill_fields(full_text, lines)
    else:
        # If is_bill is false, skip further processing and return null fields
        fields = None

    elapsed = round(time.perf_counter() - started, 3)
    logger.info(
        "Image: %-25s | is_bill: %-5s | score: %0.3f | time: %.3fs",
        image_path.name,
        str(is_bill),
        score,
        elapsed,
    )

    return {
        "file": file_str,
        "is_bill": is_bill,
        "score": score,
        "matched_signals": matched_signals,
        "fields": fields,
        "text": full_text,
        "processing_time_sec": elapsed,
    }


def _worker_wrapper(args: tuple[Path, dict]) -> dict[str, Any]:
    path, cfg = args
    return process_single_image(path, cfg)


def process_folder(
    folder_path: str | Path,
    output_dir: str | Path | None = None,
    workers: int | None = None,
    config: dict | None = None,
) -> list[dict[str, Any]]:
    """Runs batch OCR across all image files in a folder using concurrent.futures."""
    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    if config is None:
        config = load_config()

    if workers is None:
        workers = int(config.get("ocr", {}).get("workers", 2))

    # Supported image formats
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
    image_files = sorted([p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() in image_exts])

    if not image_files:
        logger.warning("No image files found in %s", folder_path)
        return []

    logger.info(
        "Starting batch OCR on %d images in '%s' with %d workers",
        len(image_files),
        folder_path.name,
        workers,
    )
    total_start = time.perf_counter()
    results = []

    tasks = [(img_path, config) for img_path in image_files]

    if workers <= 1:
        # Sequential mode
        init_worker(config)
        for task in tasks:
            results.append(_worker_wrapper(task))
    else:
        # Multiprocess batch pool
        with ProcessPoolExecutor(max_workers=workers, initializer=init_worker, initargs=(config,)) as executor:
            future_to_file = {executor.submit(_worker_wrapper, task): task[0] for task in tasks}
            for future in as_completed(future_to_file):
                img_path = future_to_file[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    logger.error("Exception processing %s: %s", img_path.name, exc)
                    results.append(
                        {
                            "file": str(img_path.resolve()),
                            "is_bill": False,
                            "score": 0.0,
                            "matched_signals": [],
                            "fields": None,
                            "text": "",
                            "error": str(exc),
                            "processing_time_sec": 0.0,
                        }
                    )

    # Sort results by filename for predictable reporting
    results.sort(key=lambda r: Path(r["file"]).name)

    total_time_sec = round(time.perf_counter() - total_start, 3)
    total_images = len(results)
    bills_detected = sum(1 for r in results if r["is_bill"])
    non_bills = total_images - bills_detected
    avg_time_sec = round(total_time_sec / max(1, total_images), 3)

    summary_banner = f"""
============================================================
BATCH OCR SUMMARY
============================================================
Total Images Processed : {total_images}
Bills Detected         : {bills_detected}
Non-Bills Detected     : {non_bills}
Total Processing Time  : {total_time_sec}s
Average Time Per Image : {avg_time_sec}s
============================================================
"""
    print(summary_banner)
    logger.info("Batch OCR complete in %.3fs (avg %.3fs/image)", total_time_sec, avg_time_sec)

    # Output writing
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        json_file = out_path / "results.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info("Saved JSON results to %s", json_file)

        csv_file = out_path / "results.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "file",
                "is_bill",
                "score",
                "vendor_name",
                "bill_date",
                "bill_number",
                "total_amount",
                "processing_time_sec",
                "matched_signals",
            ])
            for r in results:
                fields = r.get("fields") or {}
                writer.writerow([
                    Path(r["file"]).name,
                    r["is_bill"],
                    r["score"],
                    fields.get("vendor_name"),
                    fields.get("bill_date"),
                    fields.get("bill_number"),
                    fields.get("total_amount"),
                    r["processing_time_sec"],
                    ";".join(r.get("matched_signals", [])),
                ])
        logger.info("Saved CSV results to %s", csv_file)

    return results


def main():
    parser = argparse.ArgumentParser(description="PaddleOCR Batch Processing & Bill Classification")
    parser.add_argument("--folder", type=str, required=True, help="Folder containing images to process")
    parser.add_argument("--output", type=str, default=None, help="Output directory for results.json and results.csv")
    parser.add_argument("--workers", type=int, default=None, help="Number of concurrent workers (default from config)")
    args = parser.parse_args()

    process_folder(folder_path=args.folder, output_dir=args.output, workers=args.workers)


if __name__ == "__main__":
    main()

