from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ask")
async def ask_bill_snap(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chat storage and AI/RAG answering are not configured. No answer or financial value was generated.",
    )
