from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api import auth, bills, chatbot, insights, privacy, profiles, scanner
from app.core.config import get_settings
from app.database.connection import check_database_connection

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    description="Privacy-first Bill Snap API. Receipt OCR runs locally with EasyOCR; image redaction and other AI endpoints remain disabled until configured.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

for router in (auth.router, profiles.router, bills.router, scanner.router, privacy.router, insights.router, chatbot.router):
    app.include_router(router)


@app.get("/health/live", tags=["health"])
async def liveness():
    return {"status": "ok"}


@app.get("/health", tags=["health"])
async def health():
    try:
        connected = await check_database_connection()
    except SQLAlchemyError as error:
        logging.getLogger(__name__).exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection check failed.",
        ) from error
    if not connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Set DATABASE_URL and run Alembic migrations.",
        )
    return {"status": "ok", "database": "connected"}
