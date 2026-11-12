import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.database.connection import get_session, set_rls_context
from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.category import Category
from app.models.scanner_upload import ScannerUpload
from app.ml.ocr_service import OCRServiceError, ocr_service
from app.schemas.bill import BillCreate, BillPage, BillRead, BillUpdate
from app.services.bill_service import get_owned_bill
from app.services.deletion_service import permanently_delete_bill
from app.services.storage_service import download_temporary_image

router = APIRouter(prefix="/api/bills", tags=["bills"])


async def _check_category(session: AsyncSession, category_id: uuid.UUID | None) -> None:
    if category_id is not None and await session.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail="The selected category does not exist.")


@router.get("/categories", response_model=list[dict])
async def list_categories(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Category).order_by(Category.name))
    return [{"id": item.id, "name": item.name, "description": item.description, "icon": item.icon} for item in result.scalars()]


@router.post("/", response_model=BillRead, status_code=status.HTTP_201_CREATED)
async def create_bill(
    payload: BillCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_category(session, payload.category_id)
    upload = None
    if payload.upload_id:
        upload = await session.scalar(
            select(ScannerUpload).where(
                ScannerUpload.id == payload.upload_id,
                ScannerUpload.user_id == user.id,
                ScannerUpload.status == "temporary",
                ScannerUpload.bill_id.is_(None),
            )
        )
        if upload is None:
            raise HTTPException(status_code=404, detail="Temporary upload not found.")
        image = await download_temporary_image(upload.storage_path, get_settings().max_upload_bytes)
        try:
            ocr_result = await ocr_service.extract(image)
        except OCRServiceError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        classification = ocr_result["classification"]
        if classification["label"] != "bill":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "not_a_bill" if classification["label"] == "non_bill" else "bill_image_uncertain",
                    "classification": classification,
                },
            )
    bill = Bill(
        id=uuid.uuid4(),
        user_id=user.id,
        merchant_name=payload.merchant_name.strip(),
        bill_date=payload.bill_date,
        total_amount=payload.total_amount,
        currency=payload.currency.upper(),
        category_id=payload.category_id,
        payment_method=payload.payment_method,
        bill_type=payload.bill_type,
        items=[BillItem(**item.model_dump()) for item in payload.items],
    )
    session.add(bill)
    if upload is not None:
        upload.bill_id = bill.id
        upload.status = "attached"
    await session.commit()
    await set_rls_context(session, user.id, user.email)
    created = await get_owned_bill(session, user.id, bill.id)
    return created


@router.get("/search", response_model=BillPage)
async def search_bills(
    merchant: str | None = Query(default=None, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: Literal["bill_date", "total_amount", "merchant_name", "created_at"] = "bill_date",
    sort_order: Literal["asc", "desc"] = "desc",
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date.")
    filters = [Bill.user_id == user.id, Bill.is_deleted.is_(False)]
    if merchant:
        filters.append(Bill.merchant_name.ilike(f"%{merchant.strip()}%"))
    if start_date:
        filters.append(Bill.bill_date >= start_date)
    if end_date:
        filters.append(Bill.bill_date <= end_date)
    if category_id:
        filters.append(Bill.category_id == category_id)
    total = await session.scalar(select(func.count(Bill.id)).where(*filters)) or 0
    sort_column = getattr(Bill, sort_by)
    ordering = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    result = await session.execute(
        select(Bill).options(selectinload(Bill.items)).where(*filters).order_by(ordering, Bill.id).offset((page - 1) * page_size).limit(page_size)
    )
    return BillPage(items=list(result.scalars()), page=page, page_size=page_size, total=total)


@router.get("/", response_model=BillPage)
async def list_bills(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    filters = (Bill.user_id == user.id, Bill.is_deleted.is_(False))
    total = await session.scalar(select(func.count(Bill.id)).where(*filters)) or 0
    result = await session.execute(
        select(Bill)
        .options(selectinload(Bill.items))
        .where(*filters)
        .order_by(Bill.bill_date.desc(), Bill.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return BillPage(items=list(result.scalars()), page=page, page_size=page_size, total=total)


@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(
    bill_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await get_owned_bill(session, user.id, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    return bill


@router.put("/{bill_id}", response_model=BillRead)
async def update_bill(
    bill_id: uuid.UUID,
    changes: BillUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await get_owned_bill(session, user.id, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    fields = changes.model_dump(exclude_unset=True)
    if "category_id" in fields:
        await _check_category(session, fields["category_id"])
    if "merchant_name" in fields and fields["merchant_name"] is not None:
        fields["merchant_name"] = fields["merchant_name"].strip()
    if "currency" in fields and fields["currency"] is not None:
        fields["currency"] = fields["currency"].upper()
    for key, value in fields.items():
        setattr(bill, key, value)
    await session.commit()
    await set_rls_context(session, user.id, user.email)
    updated = await get_owned_bill(session, user.id, bill_id)
    return updated


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await get_owned_bill(session, user.id, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    await permanently_delete_bill(session, bill)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
