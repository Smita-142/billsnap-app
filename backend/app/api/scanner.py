import asyncio
import io
import logging
import time
import uuid
import warnings
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session, set_rls_context
from app.models.scanner_upload import ScannerUpload
from app.ml.ocr_service import OCRServiceError, ocr_service
from app.models.bill import Bill
from app.schemas.scanner import OCRRead, ScannerUploadRead
from app.models.storage_cleanup_job import StorageCleanupJob
from app.services.deletion_service import process_storage_cleanup_jobs
from app.services.storage_service import delete_storage_object, upload_temporary_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scanner", tags=["scanner"])
_recent_uploads: dict[uuid.UUID, deque[float]] = defaultdict(deque)
_rate_lock = asyncio.Lock()
_rate_check_count = 0
_ALLOWED_TYPES = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png")}
Image.MAX_IMAGE_PIXELS = 25_000_000


async def _check_upload_limit(user_id: uuid.UUID) -> None:
    global _rate_check_count
    now = time.monotonic()
    async with _rate_lock:
        recent = _recent_uploads[user_id]
        while recent and now - recent[0] >= 60:
            recent.popleft()
        _rate_check_count += 1
        if _rate_check_count % 128 == 0 and len(_recent_uploads) > 10_000:
            for inactive_id in [key for key, events in _recent_uploads.items() if not events]:
                _recent_uploads.pop(inactive_id, None)
        if len(recent) >= get_settings().upload_rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="Upload rate limit reached. Try again in a minute.")
        recent.append(now)


def _normalize_image(content: bytes, declared_type: str | None) -> tuple[bytes, str, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(io.BytesIO(content))
            image_format = source.format
            source.verify()
            source = Image.open(io.BytesIO(content))
            source.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(status_code=415, detail="The uploaded content is not a supported, valid image.") from error

    if image_format not in _ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only JPEG and PNG images are supported.")
    actual_type, extension = _ALLOWED_TYPES[image_format]
    if declared_type and declared_type.lower() not in (actual_type, "application/octet-stream"):
        raise HTTPException(status_code=415, detail="The declared content type does not match the image.")
    if source.width * source.height > 25_000_000:
        raise HTTPException(status_code=413, detail="The image dimensions exceed the supported limit.")

    source = ImageOps.exif_transpose(source)
    output = io.BytesIO()
    if image_format == "JPEG":
        source.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    else:
        source.save(output, format="PNG", optimize=True)
    return output.getvalue(), actual_type, extension


@router.post("/ocr", response_model=OCRRead)
async def extract_bill_fields(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
):
    await _check_upload_limit(user.id)
    max_bytes = get_settings().max_upload_bytes
    try:
        content = await file.read(max_bytes + 1)
    finally:
        await file.close()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Image exceeds the {max_bytes}-byte upload limit.")
    normalized, _, _ = _normalize_image(content, file.content_type)
    if len(normalized) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Re-encoded image exceeds the {max_bytes}-byte upload limit.")
    try:
        result = await ocr_service.extract(normalized)
    except OCRServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if result["classification"]["label"] == "non_bill":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "not_a_bill",
                "classification": result["classification"],
            },
        )
    return result


@router.post("/upload", response_model=ScannerUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_bill_image(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_upload_limit(user.id)
    max_bytes = get_settings().max_upload_bytes
    content = await file.read(max_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Image exceeds the {max_bytes}-byte upload limit.")
    normalized, mime_type, extension = _normalize_image(content, file.content_type)
    if len(normalized) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Re-encoded image exceeds the {max_bytes}-byte upload limit.")

    upload_id = uuid.uuid4()
    storage_path = f"temporary/{user.id}/{upload_id}{extension}"
    # Confirm database availability before creating an object that cannot be tracked.
    await session.execute(select(1))
    await upload_temporary_image(storage_path, normalized, mime_type)
    upload = ScannerUpload(
        id=upload_id,
        user_id=user.id,
        storage_path=storage_path,
        mime_type=mime_type,
        size_bytes=len(normalized),
        status="temporary",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    try:
        session.add(upload)
        await session.commit()
        await set_rls_context(session, user.id, user.email)
        await session.refresh(upload)
    except SQLAlchemyError as error:
        await session.rollback()
        try:
            await delete_storage_object(storage_path)
        except HTTPException as cleanup_error:
            logger.error("Untracked temporary upload cleanup failed: %s", cleanup_error.detail)
        raise HTTPException(status_code=503, detail="Upload metadata could not be saved.") from error

    return ScannerUploadRead(
        upload_id=upload.id,
        status=upload.status,
        mime_type=upload.mime_type,
        size_bytes=upload.size_bytes,
        created_at=upload.created_at,
    )


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_upload(
    upload_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    upload = await session.scalar(
        select(ScannerUpload).where(
            ScannerUpload.id == upload_id,
            ScannerUpload.user_id == user.id,
            ScannerUpload.status.in_(("temporary", "attached")),
        )
    )
    if upload is None:
        raise HTTPException(status_code=404, detail="Temporary or attached upload not found.")
    storage_path = upload.storage_path
    if upload.bill_id:
        bill = await session.get(Bill, upload.bill_id)
        if bill and not bill.original_image_path and not bill.sanitized_image_path:
            bill.review_status = "image_discarded"
    session.add(StorageCleanupJob(user_id=user.id, storage_path=storage_path))
    await session.delete(upload)
    await session.commit()
    await process_storage_cleanup_jobs(session, paths={storage_path}, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
