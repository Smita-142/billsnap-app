import httpx
import time
from jose import jwt
from app.core.config import get_settings

settings = get_settings()
issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
token = jwt.encode(
    {
        "sub": "12345678-1234-5678-1234-567812345678",
        "aud": "authenticated",
        "iss": issuer,
        "email": "user@example.com",
        "exp": int(time.time()) + 3600,
    },
    settings.supabase_jwt_secret.get_secret_value(),
    algorithm="HS256"
)

img_path = r"C:\Users\khush\.gemini\antigravity\brain\6bc027cd-9cc9-419e-9b29-13da67ca69e0\.user_uploaded\media_1793980140826_0cb5d6d7.jpg"

headers = {"Authorization": f"Bearer {token}"}
with open(img_path, "rb") as f:
    files = {"file": ("bill.jpg", f, "image/jpeg")}
    print("Sending OCR request to running server...")
    start = time.time()
    res = httpx.post("http://127.0.0.1:8000/api/scanner/ocr", headers=headers, files=files, timeout=90.0)
    dur = round(time.time() - start, 2)
    print("Status:", res.status_code, f"in {dur}s")
    if res.status_code == 200:
        data = res.json()
        clf = data.get("classification", {})
        print("Classification label:", clf.get("label"))
        print("Document type:", clf.get("document_type"))
        print("Confidence:", clf.get("confidence"))
        print("Should continue:", clf.get("should_continue_field_extraction"))
        print("Matched signals:", clf.get("matched_signals"))
        print("Fields:")
        for k, v in data.get("fields", {}).items():
            print(f"  {k}: {v.get('value')} (conf: {v.get('confidence')})")
    else:
        print("Error:", res.status_code, res.text)
