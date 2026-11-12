from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session, set_rls_context
from app.models.profile import Profile
from app.models.account_deletion_job import AccountDeletionJob
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.account_deletion_service import process_account_deletion

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("/me", response_model=ProfileRead)
async def get_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(Profile, user.id)
    if profile is None:
        profile = Profile(id=user.id, email=user.email)
        session.add(profile)
        await session.commit()
        await set_rls_context(session, user.id, user.email)
        await session.refresh(profile)
    return profile


@router.put("/me", response_model=ProfileRead)
async def update_profile(
    changes: ProfileUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(Profile, user.id)
    if profile is None:
        profile = Profile(id=user.id, email=user.email)
        session.add(profile)
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    if user.email:
        profile.email = user.email
    await session.commit()
    await set_rls_context(session, user.id, user.email)
    await session.refresh(profile)
    return profile


@router.patch("/me", response_model=ProfileRead, include_in_schema=False)
async def patch_profile(
    changes: ProfileUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await update_profile(changes, user, session)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    job = await session.scalar(select(AccountDeletionJob).where(AccountDeletionJob.user_id == user.id))
    if job is None:
        job = AccountDeletionJob(user_id=user.id, status="pending")
        session.add(job)
        await session.commit()
        await set_rls_context(session, user.id, user.email)
        await session.refresh(job)
    await process_account_deletion(session, job, user.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
