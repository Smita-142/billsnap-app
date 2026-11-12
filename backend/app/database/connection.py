from collections.abc import AsyncIterator

import json
from fastapi import Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.dependencies import AuthenticatedUser, get_current_user
from app.models.account_deletion_job import AccountDeletionJob

_engine = None
_session_factory = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    database_url = get_settings().database_url
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Set DATABASE_URL in backend/.env.",
        )
    if _session_factory is None:
        _engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def get_session(user: AuthenticatedUser = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    factory = _get_session_factory()
    async with factory() as session:
        await set_rls_context(session, user.id, user.email)
        deletion_status = await session.scalar(
            select(AccountDeletionJob.status).where(
                AccountDeletionJob.user_id == user.id,
                AccountDeletionJob.status != "pending",
            )
        )
        if deletion_status:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This Bill Snap account has been deleted or is being deleted.",
            )
        yield session


async def set_rls_context(session: AsyncSession, user_id, email: str | None = None) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {
            "claims": json.dumps(
                {
                    "sub": str(user_id),
                    "role": "authenticated",
                    "aud": "authenticated",
                    "email": email,
                }
            )
        },
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return _get_session_factory()


async def check_database_connection() -> bool:
    if not get_settings().database_url:
        return False
    factory = _get_session_factory()
    async with factory() as session:
        await session.execute(text("SELECT 1"))
    return True
