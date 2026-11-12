from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bill import Bill


async def get_owned_bill(session: AsyncSession, user_id, bill_id) -> Bill | None:
    result = await session.execute(
        select(Bill)
        .options(selectinload(Bill.items))
        .where(Bill.id == bill_id, Bill.user_id == user_id, Bill.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()
