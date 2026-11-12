import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy import select

from app.database.connection import get_session_factory
from app.models.account_deletion_job import AccountDeletionJob
from app.services.account_deletion_service import process_account_deletion


async def main():
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(AccountDeletionJob).where(AccountDeletionJob.status != "completed").order_by(AccountDeletionJob.created_at)
        )
        jobs = list(result.scalars())
        for job in jobs:
            try:
                await process_account_deletion(session, job)
            except HTTPException as error:
                logging.getLogger(__name__).error("Account deletion job %s remains pending: %s", job.id, error.detail)
        print(f"Account deletion jobs processed: {len(jobs)}")


if __name__ == "__main__":
    asyncio.run(main())
