from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session
from app.schemas.profile import AuthUserRead

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.get("/me", response_model=AuthUserRead)
async def verify_authenticated_user(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return AuthUserRead(id=user.id, email=user.email)
