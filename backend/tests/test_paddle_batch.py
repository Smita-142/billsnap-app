import os
import sys
import time
from pathlib import Path

# Add backend to PYTHONPATH
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image, ImageDraw

from app.ml.batch_ocr import process_folder


def create_sample_images(sample_dir: Path) -> list[Path]:
    """Generates synthetic test images covering positive and negative test cases."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    images = []

    # 1. Clear Retail Bill
    img1 = Image.new("RGB", (600, 800), color=(255, 255, 255))
    d1 = ImageDraw.Draw(img1)
    d1.text((50, 40), "SUPERMARKET FRESH MART", fill=(0, 0, 0))
    d1.text((50, 80), "Invoice No: INV-2026-9812", fill=(0, 0, 0))
    d1.text((50, 110), "Date: 15/10/2026", fill=(0, 0, 0))
    d1.text((50, 160), "1. Organic Milk 2L       $5.50", fill=(0, 0, 0))
    d1.text((50, 190), "2. Whole Wheat Bread     $3.20", fill=(0, 0, 0))
    d1.text((50, 220), "3. Olive Oil 500ml       $12.00", fill=(0, 0, 0))
    d1.text((50, 270), "Subtotal: $20.70", fill=(0, 0, 0))
    d1.text((50, 300), "Tax (10%): $2.07", fill=(0, 0, 0))
    d1.text((50, 340), "Grand Total: $22.77", fill=(0, 0, 0))
    d1.text((50, 380), "Paid by Cash: $30.00", fill=(0, 0, 0))
    p1 = sample_dir / "01_retail_receipt.jpg"
    img1.save(p1)
    images.append(p1)

    # 2. Indian GST Tax Invoice
    img2 = Image.new("RGB", (650, 850), color=(250, 250, 250))
    d2 = ImageDraw.Draw(img2)
    d2.text((60, 40), "TECH HARDWARE SOLUTIONS PVT LTD", fill=(0, 0, 0))
    d2.text((60, 80), "TAX INVOICE", fill=(0, 0, 0))
    d2.text((60, 110), "GSTIN: 27AABCT3518Q1ZV", fill=(0, 0, 0))
    d2.text((60, 140), "Bill No: THS/2026/0441", fill=(0, 0, 0))
    d2.text((60, 170), "Date: 06-11-2026", fill=(0, 0, 0))
    d2.text((60, 230), "Item: Wireless Keyboard Qty: 2 Rate: Rs. 1,200", fill=(0, 0, 0))
    d2.text((60, 260), "Item: Optical Mouse   Qty: 2 Rate: Rs. 600", fill=(0, 0, 0))
    d2.text((60, 320), "CGST 9%: Rs. 324.00", fill=(0, 0, 0))
    d2.text((60, 350), "SGST 9%: Rs. 324.00", fill=(0, 0, 0))
    d2.text((60, 400), "Grand Total: Rs. 4,248.00", fill=(0, 0, 0))
    p2 = sample_dir / "02_gst_tax_invoice.png"
    img2.save(p2)
    images.append(p2)

    # 3. Restaurant Bill
    img3 = Image.new("RGB", (550, 750), color=(255, 255, 255))
    d3 = ImageDraw.Draw(img3)
    d3.text((40, 30), "THE GOLDEN SPOON DINER", fill=(0, 0, 0))
    d3.text((40, 65), "RECEIPT", fill=(0, 0, 0))
    d3.text((40, 95), "Date: Nov 05, 2026", fill=(0, 0, 0))
    d3.text((40, 140), "Paneer Tikka            Rs. 320.00", fill=(0, 0, 0))
    d3.text((40, 170), "Butter Naan (3)         Rs. 150.00", fill=(0, 0, 0))
    d3.text((40, 200), "Dal Makhani             Rs. 280.00", fill=(0, 0, 0))
    d3.text((40, 250), "Subtotal: Rs. 750.00", fill=(0, 0, 0))
    d3.text((40, 280), "GST (5%): Rs. 37.50", fill=(0, 0, 0))
    d3.text((40, 320), "Total Payable: Rs. 787.50", fill=(0, 0, 0))
    p3 = sample_dir / "03_restaurant_receipt.jpg"
    img3.save(p3)
    images.append(p3)

    # 4. Scenery Photo (Negative Test)
    img4 = Image.new("RGB", (500, 500), color=(34, 139, 34))  # Forest green
    d4 = ImageDraw.Draw(img4)
    d4.ellipse([100, 100, 400, 400], fill=(0, 100, 0))
    p4 = sample_dir / "04_photo_nature.jpg"
    img4.save(p4)
    images.append(p4)

    # 5. General Notes Document (Negative Test - text but no bill/transaction signals)
    img5 = Image.new("RGB", (600, 700), color=(255, 255, 255))
    d5 = ImageDraw.Draw(img5)
    d5.text((40, 40), "Meeting Notes - Software Architecture Review", fill=(0, 0, 0))
    d5.text((40, 80), "We discussed the migration to asynchronous microservices.", fill=(0, 0, 0))
    d5.text((40, 110), "The engineering team agreed on the following action items:", fill=(0, 0, 0))
    d5.text((40, 140), "- Refactor database schema to optimize read queries.", fill=(0, 0, 0))
    d5.text((40, 170), "- Implement distributed caching with Redis.", fill=(0, 0, 0))
    d5.text((40, 200), "- Update integration test coverage for deployment.", fill=(0, 0, 0))
    p5 = sample_dir / "05_general_document.png"
    img5.save(p5)
    images.append(p5)

    # 6. Corrupt / Empty File (Negative test for error resilience)
    p6 = sample_dir / "06_corrupted_file.jpg"
    with open(p6, "wb") as f:
        f.write(b"NOT_A_VALID_IMAGE_HEADER_CORRUPTED_BYTES")
    images.append(p6)

    return images


def run_benchmark():
    sample_dir = BACKEND_DIR / "tests" / "sample_images"
    output_dir = BACKEND_DIR / "tests" / "benchmark_output"

    print("=" * 80)
    print("PADDLEOCR BATCH PROCESSING & BILL CLASSIFICATION BENCHMARK")
    print("=" * 80)

    print("\n1. Generating synthetic sample images...")
    images = create_sample_images(sample_dir)
    print(f"   Created {len(images)} sample images in {sample_dir}")

    print("\n2. Executing batch OCR processing (workers=2)...")
    start_time = time.perf_counter()
    results = process_folder(folder_path=sample_dir, output_dir=output_dir, workers=2)
    total_batch_time = round(time.perf_counter() - start_time, 3)

    print("\n3. RESULTS TABLE:")
    print("-" * 96)
    print(f"{'Filename':<28} | {'is_bill':<8} | {'Score':<6} | {'Vendor':<20} | {'Total':<10} | {'Time (s)':<8}")
    print("-" * 96)

    paddle_times = []
    for r in results:
        fname = Path(r["file"]).name
        is_bill_str = "YES" if r["is_bill"] else "NO"
        score_str = f"{r['score']:.2f}"
        fields = r.get("fields") or {}
        vendor = str(fields.get("vendor_name") or "-")[:20]
        total = str(fields.get("total_amount") or "-")[:10]
        time_str = f"{r['processing_time_sec']:.3f}s"
        paddle_times.append(r["processing_time_sec"])

        print(f"{fname:<28} | {is_bill_str:<8} | {score_str:<6} | {vendor:<20} | {total:<10} | {time_str:<8}")

    print("-" * 96)

    # Baseline comparison (EasyOCR baseline measured on this machine was ~58,587 ms = 58.59s per image)
    easyocr_baseline_avg_sec = 58.587
    valid_paddle_times = [t for t in paddle_times if t > 0.05]
    paddle_avg_sec = round(sum(valid_paddle_times) / max(1, len(valid_paddle_times)), 3)
    speedup = round(easyocr_baseline_avg_sec / max(0.001, paddle_avg_sec), 1)

    print("\n4. PERFORMANCE COMPARISON:")
    print(f"   Previous EasyOCR Baseline Avg : {easyocr_baseline_avg_sec:.2f}s per image")
    print(f"   New PaddleOCR Measured Avg    : {paddle_avg_sec:.2f}s per image")
    print(f"   Measured Speedup              : {speedup}x FASTER!")
    print(f"   Total Batch Runtime ({len(results)} files) : {total_batch_time:.2f}s")
    print("=" * 80)

    # Verification assertions
    assert len(results) == 6, f"Expected 6 results, got {len(results)}"
    retail_res = next(r for r in results if "retail" in r["file"])
    gst_res = next(r for r in results if "gst" in r["file"])
    photo_res = next(r for r in results if "photo" in r["file"])
    corrupt_res = next(r for r in results if "corrupted" in r["file"])

    assert retail_res["is_bill"] is True, "Retail receipt should be classified as bill"
    assert gst_res["is_bill"] is True, "GST invoice should be classified as bill"
    assert photo_res["is_bill"] is False, "Nature photo should be classified as non-bill"
    assert corrupt_res["is_bill"] is False, "Corrupt file should be safely handled"
    print("\nAll verification assertions PASSED!")


if __name__ == "__main__":
    run_benchmark()

