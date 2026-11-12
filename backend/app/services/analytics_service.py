from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser
from app.api.insights import (
    category_spending,
    merchant_spending,
    month_comparison,
    monthly_spending,
    spending_summary,
)


class AnalyticsService:
    """Entry point for SQL-backed analytics; aggregates stay in PostgreSQL."""

    async def summary(self, session: AsyncSession, user: AuthenticatedUser, year=None, month=None):
        return await spending_summary(year=year, month=month, currency=None, user=user, session=session)

    async def monthly(self, session: AsyncSession, user: AuthenticatedUser, months=12):
        return await monthly_spending(months=months, currency=None, user=user, session=session)

    async def categories(self, session: AsyncSession, user: AuthenticatedUser, year=None, month=None):
        return await category_spending(year=year, month=month, currency=None, user=user, session=session)

    async def merchants(self, session: AsyncSession, user: AuthenticatedUser, year=None, month=None, limit=10):
        return await merchant_spending(year=year, month=month, limit=limit, currency=None, user=user, session=session)

    async def comparison(self, session: AsyncSession, user: AuthenticatedUser, year=None, month=None):
        return await month_comparison(year=year, month=month, currency=None, user=user, session=session)
