import logging
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.connection import set_rls_context
from app.models.account_deletion_job import AccountDeletionJob
from app.models.bill import Bill
from app.models.chat import ChatConversation
from app.models.profile import Profile
from app.models.scanner_upload import ScannerUpload
from app.models.storage_cleanup_job import StorageCleanupJob
from app.services.deletion_service import process_storage_cleanup_jobs

logger = logging.getLogger(__name__)


async def _delete_supabase_user(user_id: uuid.UUID) -> None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth account deletion is not configured.",
        )
    key = settings.supabase_service_role_key.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
                headers={"Authorization": f"Bearer {key}", "apikey": key},
            )
        if response.status_code != 404:
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail="Supabase Auth rejected account deletion; the request can be retried.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Supabase Auth could not be reached; the request can be retried.") from error


async def _set_user_context(session: AsyncSession, user_id: uuid.UUID, email: str | None = None) -> None:
    await set_rls_context(session, user_id, email)


async def process_account_deletion(session: AsyncSession, job: AccountDeletionJob, email: str | None = None) -> None:
    if job.status == "completed":
        return
    if job.status == "pending":
        await _set_user_context(session, job.user_id, email)
        bills = await session.execute(select(Bill.original_image_path, Bill.sanitized_image_path).where(Bill.user_id == job.user_id))
        paths = {path for row in bills.all() for path in row if path}
        uploads = await session.execute(select(ScannerUpload.storage_path).where(ScannerUpload.user_id == job.user_id))
        paths.update(uploads.scalars())
        queued_paths = await session.execute(select(StorageCleanupJob.storage_path).where(StorageCleanupJob.user_id == job.user_id))
        paths.difference_update(queued_paths.scalars())
        session.add_all(StorageCleanupJob(user_id=job.user_id, storage_path=path) for path in paths)
        job.status = "deletion_requested"
        await session.commit()

    if job.status == "deletion_requested":
        try:
            await _delete_supabase_user(job.user_id)
        except HTTPException as error:
            await _set_user_context(session, job.user_id, email)
            job.status = "pending"
            job.last_error = error.detail[:500]
            await session.commit()
            raise
        job.status = "auth_deleted"
        job.last_error = None
        await session.commit()

    if job.status != "data_deleted":
        await _set_user_context(session, job.user_id, email)
        try:
            bills = await session.execute(select(Bill.original_image_path, Bill.sanitized_image_path).where(Bill.user_id == job.user_id))
            paths = {path for row in bills.all() for path in row if path}
            uploads = await session.execute(select(ScannerUpload.storage_path).where(ScannerUpload.user_id == job.user_id))
            paths.update(uploads.scalars())
            session.add_all(StorageCleanupJob(user_id=job.user_id, storage_path=path) for path in paths)
            await session.execute(delete(ScannerUpload).where(ScannerUpload.user_id == job.user_id))
            await session.execute(delete(Bill).where(Bill.user_id == job.user_id))
            await session.execute(delete(ChatConversation).where(ChatConversation.user_id == job.user_id))
            await session.execute(delete(Profile).where(Profile.id == job.user_id))
            job.status = "data_deleted"
            job.last_error = None
            await session.commit()
        except SQLAlchemyError as error:
            await session.rollback()
            logger.exception("Database cleanup failed after Supabase Auth deletion for job %s", job.id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase Auth account was deleted, but database cleanup is queued for retry.",
            ) from error

    await _set_user_context(session, job.user_id, email)
    _, pending = await process_storage_cleanup_jobs(session, user_id=job.user_id)
    if pending:
        job.last_error = "One or more storage objects could not be removed yet."
        await session.commit()
        return
    await _set_user_context(session, job.user_id, email)
    job.status = "completed"
    job.last_error = None
    await session.commit()
