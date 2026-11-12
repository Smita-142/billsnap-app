# Bill Snap API

FastAPI/PostgreSQL backend isolated from the existing React application. It verifies Supabase access tokens, scopes database work to the verified user, and applies PostgreSQL Row Level Security as a second boundary.

## Requirements

- Python 3.11+
- PaddleOCR models are automatically cached locally upon first use (CPU mode with angle classification enabled).
- A Supabase project (PostgreSQL, Auth, and a private Storage bucket)
- A database connection URL with permission to apply migrations and `SET ROLE authenticated`

## Windows setup

From PowerShell:

```powershell
cd "C:\Users\khush\OneDrive\Desktop\New folder (2)\Bill Snap\backend"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with the Supabase project settings. Do not commit `.env` or use the service-role key in the React application.

### Supabase settings

1. Create a Supabase project and a **private** Storage bucket (for example `bill-images`).
2. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET`. The service-role key is backend-only and is used only for private Storage and the Auth admin deletion API.
3. Configure `SUPABASE_JWT_SECRET` for projects using legacy HS256 JWT signing. For asymmetric RS256/ES256 signing, set `SUPABASE_URL`; the backend loads and caches the project's public JWKS for signature verification. Tokens must have `aud=authenticated`, a subject, and an unexpired `exp`.
4. Set `DATABASE_URL` to the Supabase **direct** PostgreSQL connection string using the SQLAlchemy async driver, e.g. `postgresql+asyncpg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?ssl=require`. URL-encode special characters in the password. Keep this value private.
5. Set `CORS_ORIGINS` to a comma-separated allowlist of frontend origins, such as `http://localhost:3000,https://your-domain.example`.
6. Configure Supabase Auth email confirmation, password rules, and redirect URLs in the Supabase dashboard. The frontend should use Supabase Auth for sign-up/sign-in and send its access token as `Authorization: Bearer <access-token>` to this API. This backend does not create a second password store.

The migration expects Supabase's `auth.users`, `auth.uid()`, and `anon`/`authenticated` database roles. It creates application tables, default categories, RLS policies and grants. API sessions set the verified subject as transaction-local claims and switch to the `authenticated` role. Use a Supabase database connection role that is permitted to assume `authenticated`; do not connect as an untrusted browser/database role.

## Migrations and run

```powershell
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Run these commands from the `backend` directory. API docs are at `http://localhost:8000/docs` and `/redoc`; liveness is `/health/live`. `/health` performs a real database check and returns HTTP 503 until `DATABASE_URL` is configured and reachable.

## API

Protected endpoints require a valid Supabase access token. IDs in URLs are always checked against the verified user; a `user_id` from the request body is never used for authorization.

| Method | Path | Description |
|---|---|---|
| GET | `/api/auth/me` | Verify token and return authenticated identity |
| GET, PUT | `/api/profiles/me` | Read or update the current profile |
| DELETE | `/api/profiles/me` | Delete Supabase Auth user and queue deletion of owned rows/files |
| GET | `/api/bills/categories` | List default categories |
| POST | `/api/bills/` | Create bill and optional line items; accepts an owned `upload_id` |
| GET | `/api/bills/` | List bills with page/page_size |
| GET | `/api/bills/search` | Filter by merchant, start_date, end_date, category_id; sort_by and sort_order |
| GET, PUT, DELETE | `/api/bills/{bill_id}` | Retrieve, update, or permanently delete an owned bill |
| POST | `/api/scanner/upload` | Validate/re-encode JPG/PNG and store a tracked temporary image |
| POST | `/api/scanner/ocr` | Authenticated, in-memory receipt OCR preview; does not store or attach the image |
| DELETE | `/api/scanner/uploads/{upload_id}` | Discard an owned temporary/attached upload |
| POST | `/api/privacy/detect` | Returns 501 until a real detector is configured |
| GET | `/api/privacy/{bill_id}/detections` | List stored privacy event metadata |
| POST | `/api/privacy/{bill_id}/approve` | Record user review; does not assert pixel redaction |
| POST | `/api/privacy/{bill_id}/redact` | Returns 501 until real pixel redaction is configured |
| GET | `/api/insights/summary` | SQL totals, count, average, highest category |
| GET | `/api/insights/monthly` | Monthly totals and bill counts |
| GET | `/api/insights/categories` | Category totals/counts |
| GET | `/api/insights/merchants` | Merchant totals/counts |
| GET | `/api/insights/comparison` | Current/previous month comparison |
| POST | `/api/chat/ask` | Returns 501; chatbot is intentionally disabled |

Analytics accept an optional ISO currency query parameter (e.g. `?currency=INR`). When a selected period contains more than one currency, a currency must be specified; unlike currencies are never added together. Bill amounts use PostgreSQL `NUMERIC`, not floating-point.

Example:

```powershell
$headers = @{ Authorization = "Bearer $accessToken" }
Invoke-RestMethod -Headers $headers -Uri "http://localhost:8000/api/bills/?page=1&page_size=20"
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" -Uri "http://localhost:8000/api/bills/" -Body '{"merchant_name":"Cafe","bill_date":"2026-11-06","total_amount":"420.50","currency":"INR"}'
```

Upload example:

```powershell
Invoke-RestMethod -Method Post -Headers $headers -Form @{ file = Get-Item ".\receipt.jpg" } -Uri "http://localhost:8000/api/scanner/upload"
Invoke-RestMethod -Method Post -Headers $headers -Form @{ file = Get-Item ".\receipt.jpg" } -Uri "http://localhost:8000/api/scanner/ocr"
```

`/api/scanner/ocr` accepts JPG/PNG within `MAX_UPLOAD_BYTES` and the existing 25-megapixel image limit. It runs EasyOCR locally on CPU using a cached English/Hindi/Marathi reader, compares raw and preprocessed variants, and returns recognized text, boxes, field confidence, classification, reasons, and processing times. Classification has `bill`, `non_bill`, and `uncertain` outcomes with user-facing `message`, evidence, and continuation flags. Definite non-bills return HTTP 422 with `detail.code=not_a_bill`; uncertain images return a review message and no extracted fields. A final `POST /api/bills/` that attaches an uploaded image re-downloads and classifies it again before creating a bill, so temporary uploads cannot bypass the classification gate. The OCR preview does not save an image or bill.

The classifier is a conservative hybrid baseline combining receipt transaction structure, OCR line positions, image layout, and hard negative cues for menus, identity documents, and screenshots. No dedicated real-world training or validation set was supplied, so no MobileNet model was trained, no decision threshold was calibrated, and `classification.confidence` is explicitly an uncalibrated evidence-coverage score—not a correctness probability. A handwritten receipt with poor OCR and non-English or unusual layouts may be flagged uncertain. Screenshots or images with convincing transaction text may still require human review. EasyOCR 1.7.2 accepted `en+hi`, `en+mr`, and `en+hi+mr` CPU reader configurations in a no-model-download compatibility check; actual recognition accuracy still requires labeled real images.

## Privacy, uploads, and deletion

- Uploads are limited by `MAX_UPLOAD_BYTES`, user-rate-limited per process, checked against actual image contents using Pillow, dimension-limited, and re-encoded to remove image metadata. The re-encoded pixels can still contain personal information.
- `/api/scanner/upload` stores a temporary image in the private Supabase bucket. `/api/scanner/ocr` processes its bounded in-memory upload locally and does not write it to Supabase or send it to an external provider. Neither endpoint returns a public image URL.
- Temporary/unreviewed uploads expire after 24 hours. Schedule `python -m app.scripts.cleanup_temporary_uploads` with Windows Task Scheduler. Users can also explicitly discard an upload.
- `POST /api/privacy/{bill_id}/approve` records that the user reviewed the bill. If `retain_original_consent` is true and an image is attached, the path is retained as the original by explicit consent. This does not mark the image sanitized.
- Privacy detection, pixel-level redaction, embeddings, RAG, and chatbot answers are not implemented. Classification confidence is not calibrated, and classification does not replace user review.
- Bill deletion is permanent in PostgreSQL. Storage paths are placed in an outbox in the same DB transaction and cleanup is attempted immediately. Retry failures with `python -m app.scripts.retry_storage_cleanup`.
- Account deletion first requests Supabase Auth deletion, then removes the user's database records and queues image cleanup. A deletion tombstone blocks further API access even if a locally verified JWT has not expired. If a cloud call fails, retry pending work with `python -m app.scripts.process_account_deletions`; retry Storage outbox jobs with `python -m app.scripts.retry_storage_cleanup`. Supabase/backups may have provider-defined retention and are not represented as instantly erased.

## Database design

`profiles`, `categories`, `bills`, `bill_items`, `extraction_results`, `privacy_events`, `chat_conversations`, and `chat_messages` are the core normalized tables. `scanner_uploads`, `storage_cleanup_jobs`, and `account_deletion_jobs` support temporary upload tracking and retryable deletion. UUIDs, indexes, foreign keys/cascades, UTC timestamps, and RLS policies are defined in the initial migration. Default categories are seeded by that migration.

`rag_chunks` and pgvector are intentionally absent until sanitized text and an actual retrieval service exist.

## Tests

The test suite uses an isolated SQLite database for API behavior and does not require Supabase credentials or downloading OCR models:

```powershell
python -m pytest -q
```

It exercises authentication claims, profiles, bill CRUD/pagination/search, cross-user access denial, analytics currency handling, image validation/metadata stripping, OCR extraction and preprocessing, OCR API privacy and upload limits, receipt classification and attached-image gating, honest privacy-service failures, account deletion, and API docs. PostgreSQL-specific RLS/migration behavior must still be verified against a disposable Supabase/PostgreSQL project before production deployment.

Classification unit fixtures are generated synthetic images with annotated OCR text, not real validation images. Run `python -m pytest tests/test_classification.py -q -s` to see the three-class confusion matrix and binary bill-vs-rejected precision, recall, F1, and false acceptance rate. These fixture metrics verify the implemented rules only; they do not estimate real-world performance or calibrate confidence. Keep classifier validation data separate from any future model training data.

### OCR benchmark

The labeled dataset structure and repeatable raw-versus-preprocessed evaluation are in [`benchmarks/ocr/README.md`](./benchmarks/ocr/README.md). Add 15 real bills and 5 real non-bills with manually verified expected OCR text and fields before running `python -m app.scripts.evaluate_ocr`. The starter manifest is empty by design; no sample images or ground truth are bundled, and benchmark accuracy is not claimed until that dataset exists.
