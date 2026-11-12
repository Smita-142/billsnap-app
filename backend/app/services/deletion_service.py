import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.scanner_upload import ScannerUpload
from app.models.storage_cleanup_job import StorageCleanupJob
from app.database.connection import set_rls_context
from app.services.storage_service import delete_storage_object

logger = logging.getLogger(__name__)


async def permanently_delete_bill(session: AsyncSession, bill: Bill) -> None:
    upload_result = await session.execute(select(ScannerUpload).where(ScannerUpload.bill_id == bill.id))
    uploads = list(upload_result.scalars())
    paths = {path for path in (bill.original_image_path, bill.sanitized_image_path) if path}
    paths.update(upload.storage_path for upload in uploads)
    for path in paths:
        session.add(StorageCleanupJob(user_id=bill.user_id, storage_path=path))
    for upload in uploads:
        await session.delete(upload)
    await session.delete(bill)
    await session.commit()

    await process_storage_cleanup_jobs(session, paths=paths, user_id=bill.user_id)


async def process_storage_cleanup_jobs(
    session: AsyncSession,
    paths: set[str] | None = None,
    limit: int = 100,
    user_id: uuid.UUID | None = None,
) -> tuple[int, int]:
    if paths is not None and not paths:
        return 0, 0
    if user_id is not None:
        await set_rls_context(session, user_id)
    statement = select(StorageCleanupJob).order_by(StorageCleanupJob.created_at).limit(limit)
    if paths:
        statement = statement.where(StorageCleanupJob.storage_path.in_(paths))
    if user_id is not None:
        statement = statement.where(StorageCleanupJob.user_id == user_id)
    result = await session.execute(statement)
    completed = failed = 0
    for job in list(result.scalars()):
        try:
            await delete_storage_object(job.storage_path)
        except HTTPException as error:
            logger.warning("Storage cleanup remains pending for job %s: %s", job.id, error)
            job.last_error = str(error)[:500]
            await session.commit()
            failed += 1
            await _restore_context(session, user_id)
        else:
            await session.delete(job)
            await session.commit()
            completed += 1
            await _restore_context(session, user_id)
    return completed, failed


async def _restore_context(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    await set_rls_context(session, user_id)
