# Bill Snap - OCR & Bill Classification Engine

Bill Snap features a high-performance OCR pipeline powered by **PaddleOCR** with automatic bill vs non-bill classification, regex heuristic field extraction, and multiprocess batch folder processing.

---

## 1. Setup & Installation

Ensure you have Python 3.11+ installed.

```bash
# Navigate to backend directory
cd backend

# Activate your virtual environment
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

> **Note on Windows CPU Execution**: PaddleX requires setting `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False` to ensure optimal and bug-free execution on x86 Windows platforms without oneDNN instruction incompatibilities. This is preconfigured in `ocr_service.py` and `batch_ocr.py`.

---

## 2. Configuration (`backend/app/ml/ocr_config.yaml`)

OCR and classification parameters can be tuned in `backend/app/ml/ocr_config.yaml`:

```yaml
ocr:
  engine: "paddleocr"
  language: "en"          # Primary OCR language ('en', 'hi', etc.)
  use_gpu: false          # Set to true for CUDA GPU acceleration
  use_angle_cls: true     # Orientation and textline angle classification
  max_long_side: 1800     # Resizes longest side (never upscales)
  workers: 2              # Number of parallel worker processes

classification:
  threshold: 0.35         # Score threshold for bill vs non-bill decision
  keywords:
    - "tax invoice"
    - "invoice no"
    - "bill no"
    - "grand total"
    - "subtotal"
    - "invoice"
    - "receipt"
    - "bill"
    - "total"
    - "gst"
    - "cgst"
    - "sgst"
    - "igst"
    - "tax"
    - "amount"
    - "qty"
    - "rate"
    - "cash"
    - "paid"
    - "due"
  weights:
    keyword: 1.0
    currency: 1.5         # ₹, Rs, INR, $
    date: 1.0             # DD/MM/YYYY, YYYY-MM-DD, etc.
    gstin: 2.0            # 15-character GSTIN format
```

---

## 3. Batch / Folder Processing

Process an entire folder of images in parallel with `concurrent.futures.ProcessPoolExecutor`:

```bash
# Run batch OCR from backend directory:
python -m app.ml.batch_ocr --folder path/to/images --output path/to/output --workers 2
```

### Outputs Generated:
- **Per-image timing logs**: Real-time progress in stdout
- **Batch summary table**: Total processed, bills detected, non-bills, average time
- **`results.json`**: Structured JSON array per image:
  ```json
  {
    "file": "path/to/receipt.jpg",
    "is_bill": true,
    "score": 1.0,
    "matched_signals": ["keyword:invoice", "keyword:total", "pattern:currency"],
    "fields": {
      "vendor_name": "Fresh Mart",
      "bill_date": "15/10/2026",
      "bill_number": "INV-2026-9812",
      "total_amount": 22.77
    },
    "text": "Extracted OCR text...",
    "processing_time_sec": 1.84
  }
  ```
- **`results.csv`**: Tabular export with columns: `file`, `is_bill`, `score`, `vendor_name`, `bill_date`, `bill_number`, `total_amount`, `processing_time_sec`, `matched_signals`.

---

## 4. Testing & Verification

Run the comprehensive test suite and benchmark:

```bash
# Run backend pytest suite (68 tests)
pytest backend/tests/ -v

# Run PaddleOCR batch benchmark & verification script
python backend/tests/test_paddle_batch.py
```

---

## 5. ML Evaluation & Results Table (20 Images)

Evaluated on 15 real bills (including crumpled, angled, blurry, and multilingual receipts) and 5 non-bill negative controls:

| # | Image Type & Condition | Identified as Bill? | Merchant | Date | Total Amount | Category Suggested | Notes |
|---|------------------------|:-------------------:|:--------:|:----:|:------------:|:------------------:|-------|
| 1 | Clear retail grocery receipt | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Groceries | Clear print, vertical line layout |
| 2 | GST Tax Invoice (Hardware/Tech) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Electronics / Other | GSTIN + SGST/CGST breakdown detected |
| 3 | Restaurant dine-in bill (Domino's Pizza) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Food & Dining | Subtotal, VAT, Rounding off detected |
| 4 | Cafe receipt (The Golden Spoon) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Food & Dining | Itemized list and total payable |
| 5 | Utility Bill (MSEDCL Electricity bill) | ✅ Yes | ❌ Wrong (`HETTAARUT`) | ✅ Right | ✅ Right (`₹410.00`) | Utilities | Logo/header misread; amount correct |
| 6 | College Fee Receipt (A.P. Shah Institute) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right (`₹17,429`) | Education / Other | "Receipt" keyword + fee breakdown |
| 7 | Crumpled supermarket slip | ✅ Yes | ✅ Right | ❌ Wrong | ✅ Right | Groceries | Fold crease obscured the date line |
| 8 | Angled phone photo of pharmacy receipt | ✅ Yes | ❌ Wrong (`D0`) | ✅ Right | ❌ Wrong (`276`) | Healthcare | Skew + lighting caused decimal drop |
| 9 | Faded thermal fuel receipt | ✅ Yes | ✅ Right | ✅ Right | ❌ Wrong | Transport / Fuel | Low thermal contrast faded total digits |
| 10 | International invoice (`Fatura`) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Shopping | Multilingual settlement keyword |
| 11 | Digital design invoice (PDF screenshot) | ✅ Yes | ❌ Wrong (`NO`) | ✅ Right | ✅ Right (`$1540`) | Services | Header "NO" picked from "INVOICE NO" |
| 12 | Dimly lit restaurant receipt | ✅ Yes | ✅ Right | ❌ Wrong | ✅ Right | Food & Dining | Date blurred by camera motion |
| 13 | Handwritten local grocery slip | ✅ Yes | ❌ Wrong | ❌ Wrong | ❌ Wrong | Groceries | Mobile OCR trained on printed typography |
| 14 | Long supermarket receipt (folded) | ✅ Yes | ✅ Right | ✅ Right | ❌ Wrong | Groceries | Fold obscured "Grand Total" line |
| 15 | Delivery app printout (Swiggy/Zomato) | ✅ Yes | ✅ Right | ✅ Right | ✅ Right | Food & Dining | Order layout recognized cleanly |
| 16 | **Non-bill**: Selfie / Portrait photo | ❌ No (Rejected) | — | — | — | — | Correctly rejected: photo terms |
| 17 | **Non-bill**: Government ID Card (Aadhaar) | ❌ No (Rejected) | — | — | — | — | Correctly rejected: ID signals |
| 18 | **Non-bill**: Mobile phone screenshot | ❌ No (Rejected) | — | — | — | — | Correctly rejected: OS UI status bar |
| 19 | **Non-bill**: Meeting notes / Text doc | ❌ No (Rejected) | — | — | — | — | Correctly rejected: no transaction signals |
| 20 | **Non-bill**: Landscape / Nature photo | ❌ No (Rejected) | — | — | — | — | Correctly rejected: zero text density |

---

## 6. Where It Fails & Why (Honest Failure Analysis)

1. **Stylized Logos vs. Top Text**:
   - **Failure**: In angled or logo-heavy bills (e.g., regional utility bills or receipts starting with `"INVOICE NO"`), the top-line heuristic occasionally extracts an acronym or label (`"NO"`, `"D0"`) rather than the true business entity.
   - **Why**: Without a heavy fine-tuned Named Entity Recognition (NER) model, pure geometric top-of-page line ranking picks header text instead of company names when the logo is rendered as artwork.
2. **Creased & Angled Photos**:
   - **Failure**: Folds across numeric columns can cause OCR character splitting (e.g., reading `₹420.00` as `42` or `276`).
   - **Why**: Fast CPU inference disables heavy 3D unwarping models (like UVDoc) to preserve response speed, trading off distortion resilience on heavy folds.
3. **Handwritten Slips**:
   - **Failure**: Handwritten bill amounts and dates fail recognition.
   - **Why**: Mobile detection/recognition models (`PP-OCRv4_mobile`) are optimized for printed Latin and Devanagari typography and lack handwriting stroke feature sets.
4. **UX Safety Valve**:
   - To counteract these ML failure modes, every extracted field displays a confidence badge (`high`, `medium`, or `uncertain · review`), and **nothing is committed to the database until the user explicitly inspects, corrects, and confirms the fields on the review screen**.

---

## 7. Reflections: What I Like & What I Would Change

### What I Like:
- **Rock-solid privacy and rejection logic**: Non-bills (selfies, ID cards, landscape shots) are rejected gracefully with clear, polite explanations before field extraction begins.
- **The interactive review step**: Users never get stuck with wrong data; the screen highlights uncertain fields in yellow so corrections take only 2–3 seconds.
- **Architecture**: A modular pipeline cleanly separating Image Preprocessing → Detection & Recognition → Rule & Pattern Classification → Field Heuristics → Supabase PostgreSQL.

### What I Would Change:
- **Edge on-device classification**: Run a lightweight MobileNet classifier directly in WebAssembly/ONNX in the browser to instantly flag non-bills with zero server roundtrips.
- **LLM/VLM Fallback for Low Confidence**: Use a tiny multimodal model (e.g., Gemini Flash or SmolVLM) exclusively as a fallback when rule confidence is below 0.60 to resolve complex merchant logos and handwritten amounts.
- **Client-Side Document Cropper**: Add automatic edge-detection and perspective quad-warping before upload so shadows and desk backgrounds are stripped automatically.

