from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session
from app.models.bill import Bill
from app.models.category import Category
from app.schemas.insights import SpendingSummary

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _active_user_bills(user: AuthenticatedUser):
    return (Bill.user_id == user.id, Bill.is_deleted.is_(False))


def _money_string(value) -> str:
    return format(Decimal(value or 0).quantize(Decimal("0.01")), "f")


async def _resolve_currency(
    session: AsyncSession,
    user: AuthenticatedUser,
    filters: list,
    currency: str | None,
) -> str:
    if currency is not None:
        return currency.upper()
    result = await session.execute(select(Bill.currency).where(*filters).distinct())
    values = list(result.scalars())
    if len(values) > 1:
        raise HTTPException(
            status_code=422,
            detail="This period contains multiple currencies. Specify the currency query parameter to avoid combining unlike amounts.",
        )
    return values[0] if values else "INR"


@router.get("/summary", response_model=SpendingSummary)
async def spending_summary(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    today = datetime.now(timezone.utc).date()
    year = year or today.year
    month = month or today.month
    filters = list(_active_user_bills(user))
    filters.extend((extract("year", Bill.bill_date) == year, extract("month", Bill.bill_date) == month))
    selected_currency = await _resolve_currency(session, user, filters, currency)
    filters.append(Bill.currency == selected_currency)
    totals = await session.execute(
        select(
            func.coalesce(func.sum(Bill.total_amount), Decimal("0.00")),
            func.count(Bill.id),
            func.coalesce(func.avg(Bill.total_amount), Decimal("0.00")),
        ).where(*filters)
    )
    total, count, average = totals.one()
    highest = await session.scalar(
        select(Category.name)
        .join(Bill, Bill.category_id == Category.id)
        .where(*filters)
        .group_by(Category.name)
        .order_by(func.sum(Bill.total_amount).desc(), Category.name)
        .limit(1)
    )
    return SpendingSummary(total_amount=total, bill_count=count, average_amount=average, highest_spending_category=highest, currency=selected_currency)


@router.get("/monthly")
async def monthly_spending(
    months: int = Query(default=12, ge=1, le=36),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    filters = list(_active_user_bills(user))
    selected_currency = await _resolve_currency(session, user, filters, currency)
    filters.append(Bill.currency == selected_currency)
    year_column = extract("year", Bill.bill_date).label("year")
    month_column = extract("month", Bill.bill_date).label("month")
    result = await session.execute(
        select(year_column, month_column, func.sum(Bill.total_amount).label("total_amount"), func.count(Bill.id).label("bill_count"))
        .where(*filters)
        .group_by(year_column, month_column)
        .order_by(year_column.desc(), month_column.desc())
        .limit(months)
    )
    rows = list(result.all())
    rows.reverse()
    return [
        {
            "month": date(int(row.year), int(row.month), 1),
            "total_amount": _money_string(row.total_amount),
            "bill_count": row.bill_count,
        }
        for row in rows
    ]


@router.get("/categories")
async def category_spending(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    filters = list(_active_user_bills(user))
    if year is not None:
        filters.append(extract("year", Bill.bill_date) == year)
    if month is not None:
        filters.append(extract("month", Bill.bill_date) == month)
    selected_currency = await _resolve_currency(session, user, filters, currency)
    filters.append(Bill.currency == selected_currency)
    result = await session.execute(
        select(Category.id, Category.name, func.sum(Bill.total_amount).label("total_amount"), func.count(Bill.id).label("bill_count"))
        .join(Bill, Bill.category_id == Category.id)
        .where(*filters)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Bill.total_amount).desc())
    )
    return [
        {"category_id": row.id, "category": row.name, "total_amount": _money_string(row.total_amount), "bill_count": row.bill_count}
        for row in result.all()
    ]


@router.get("/merchants")
async def merchant_spending(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    filters = list(_active_user_bills(user))
    if year is not None:
        filters.append(extract("year", Bill.bill_date) == year)
    if month is not None:
        filters.append(extract("month", Bill.bill_date) == month)
    selected_currency = await _resolve_currency(session, user, filters, currency)
    filters.append(Bill.currency == selected_currency)
    result = await session.execute(
        select(Bill.merchant_name, func.sum(Bill.total_amount).label("total_amount"), func.count(Bill.id).label("bill_count"))
        .where(*filters)
        .group_by(Bill.merchant_name)
        .order_by(func.sum(Bill.total_amount).desc())
        .limit(limit)
    )
    return [
        {"merchant": row.merchant_name, "total_amount": _money_string(row.total_amount), "bill_count": row.bill_count}
        for row in result.all()
    ]


@router.get("/comparison")
async def month_comparison(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    currency: str | None = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    current = datetime.now(timezone.utc).date()
    year, month = year or current.year, month or current.month
    current_start = date(year, month, 1)
    previous_start = date(year - (month == 1), 12 if month == 1 else month - 1, 1)
    next_start = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    period_filters = [*_active_user_bills(user), Bill.bill_date >= previous_start, Bill.bill_date < next_start]
    selected_currency = await _resolve_currency(session, user, period_filters, currency)

    async def total_for(start: date, end: date):
        return await session.scalar(
            select(func.coalesce(func.sum(Bill.total_amount), Decimal("0.00"))).where(
                *_active_user_bills(user), Bill.currency == selected_currency, Bill.bill_date >= start, Bill.bill_date < end
            )
        )

    current_total = Decimal(await total_for(current_start, next_start) or 0)
    previous_total = Decimal(await total_for(previous_start, current_start) or 0)
    delta = current_total - previous_total
    percentage = None if previous_total == 0 else (delta / previous_total * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "current_month": {"year": year, "month": month, "total_amount": _money_string(current_total)},
        "previous_month": {"year": previous_start.year, "month": previous_start.month, "total_amount": _money_string(previous_total)},
        "change_amount": _money_string(delta),
        "change_percent": None if percentage is None else format(percentage, "f"),
        "currency": selected_currency,
    }
