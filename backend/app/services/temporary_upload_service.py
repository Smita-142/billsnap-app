from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.scanner_upload import ScannerUpload
from app.models.storage_cleanup_job import StorageCleanupJob
from app.services.deletion_service import process_storage_cleanup_jobs


async def purge_expired_temporary_uploads(session: AsyncSession, batch_size: int = 100) -> tuple[int, int]:
    result = await session.execute(
        select(ScannerUpload)
        .where(
            ScannerUpload.expires_at <= datetime.now(timezone.utc),
            ScannerUpload.status.in_(("temporary", "attached")),
        )
        .order_by(ScannerUpload.expires_at)
        .limit(batch_size)
    )
    uploads = list(result.scalars())
    paths = {upload.storage_path for upload in uploads}
    for upload in uploads:
        if upload.bill_id:
            bill = await session.get(Bill, upload.bill_id)
            if bill and not bill.original_image_path and not bill.sanitized_image_path:
                bill.review_status = "image_expired"
        session.add(StorageCleanupJob(user_id=upload.user_id, storage_path=upload.storage_path))
        await session.delete(upload)
    await session.commit()
    _, failed = await process_storage_cleanup_jobs(session, paths=paths)
    return len(uploads), failed
