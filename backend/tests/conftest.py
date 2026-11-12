import time
import uuid

import httpx
import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import _jwks_cache
from app.database.base import Base
import app.models  # noqa: F401
from app.database.connection import get_session
from app.main import app

JWT_SECRET = "test-only-signing-secret-not-for-production-use"
TEST_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def access_token(user_id=TEST_USER_ID):
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": "authenticated",
            "email": "test@example.com",
            "exp": int(time.time()) + 600,
        },
        JWT_SECRET,
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    _jwks_cache.clear()
    database_path = tmp_path / "test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.test_session_factory = session_factory

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api_client:
        yield api_client
    app.dependency_overrides.clear()
    del app.state.test_session_factory
    await engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {access_token()}"}
