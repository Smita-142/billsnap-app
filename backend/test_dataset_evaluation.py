import os
import sys
import time
from pathlib import Path

# Paddle environment flags for Windows CPU
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from app.ml.ocr_service import _extract_sync

dataset_dir = Path("tests/dataset_bills")
images = sorted(list(dataset_dir.glob("*.jpg")) + list(dataset_dir.glob("*.png")))

print(f"============================================================")
print(f"DATASET EVALUATION: {len(images)} images found in {dataset_dir}")
print(f"============================================================")

results = []
# Test user uploaded images first, then a batch of dataset images
priority_names = ["user_msedcl_electricity_bill.jpg", "user_college_fee_receipt.jpg"]
ordered_images = [img for name in priority_names for img in images if img.name == name]
ordered_images += [img for img in images if img.name not in priority_names]

# Test first 8 images (including the 2 real user uploads)
test_batch = ordered_images[:8]

for i, img_path in enumerate(test_batch, 1):
    print(f"\n[{i}/{len(test_batch)}] Processing: {img_path.name}")
    try:
        with open(img_path, "rb") as f:
            img_bytes = f.read()

        t0 = time.perf_counter()
        res = _extract_sync(img_bytes)
        elapsed = round(time.perf_counter() - t0, 2)

        clf = res.get("classification", {})
        fields = res.get("fields", {})
        merchant = fields.get("merchant_name", {}).get("value")
        date = fields.get("bill_date", {}).get("value")
        total = fields.get("total_amount", {}).get("value")
        curr = fields.get("currency", {}).get("value")

        is_bill = clf.get("is_bill", False) or clf.get("label") == "bill"
        print(f"  -> Result: is_bill={is_bill} | label={clf.get('label')} | doc_type={clf.get('document_type')} | conf={clf.get('confidence')}")
        print(f"  -> Fields: merchant='{merchant}' | date='{date}' | total='{total}' | currency='{curr}'")
        print(f"  -> Time: {elapsed}s")

        results.append({
            "file": img_path.name,
            "is_bill": is_bill,
            "label": clf.get("label"),
            "doc_type": clf.get("document_type"),
            "confidence": clf.get("confidence"),
            "merchant": merchant,
            "date": date,
            "total": total,
            "time_s": elapsed,
        })
    except Exception as e:
        print(f"  -> ERROR: {e}")
        results.append({
            "file": img_path.name,
            "error": str(e)
        })

print("\n" + "=" * 60)
print("EVALUATION SUMMARY")
print("=" * 60)
passed = sum(1 for r in results if r.get("is_bill"))
print(f"Processed: {len(results)} | Bills Identified: {passed}/{len(results)}")
for r in results:
    if "error" in r:
        print(f"  [ERR] {r['file']}: {r['error']}")
    else:
        status_icon = "PASS" if r["is_bill"] else "FAIL"
        print(f"  [{status_icon}] {r['file'][:35]:35} | label={r['label']:8} | type={r['doc_type']:8} | total={str(r['total']):10} | {r['time_s']}s")
print("=" * 60)
