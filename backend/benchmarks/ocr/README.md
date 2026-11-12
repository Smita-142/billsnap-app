# OCR evaluation dataset

Put consenting, locally held sample images in `images/` and add one manually verified row per image to `manifest.csv`.
Use exactly 20 images: 15 genuine bills and 5 non-bill images. The 15 bills should collectively cover clear,
blurry, tilted, crumpled, low-light, handwritten, long, Hindi, and Marathi examples. Expected text and field
values must be transcribed from the actual image; do not infer them from OCR output. Use ISO dates (`YYYY-MM-DD`)
and decimal amounts without currency symbols for field annotations. Leave `expected_tax` blank only when tax is
not applicable or is not shown; expected text may be blank only for a manually confirmed image with no text.

The starter manifest intentionally contains only its header. No sample images or ground truth were supplied,
so no benchmark accuracy or timing results are claimed.

From `backend/`, after installing requirements and allowing EasyOCR to download its models on first use:

```powershell
python -m app.scripts.evaluate_ocr
```

The evaluator writes `results.csv` (40 rows: raw and preprocessed for every image) and records CER, WER, exact
merchant/date/total/tax matches, classification, processing time, and field/classification failure reasons.
Override the paths with `--manifest`, `--images`, and `--output`. The command refuses to run unless the
annotated dataset has exactly 15 bills and 5 non-bills. Treat receipt images and the generated result file as
sensitive data; keep both local and out of source control.
