import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AuthenticatedUser, get_current_user
from app.database.connection import get_session
from app.models.bill import Bill
from app.models.privacy_event import PrivacyEvent
from app.models.scanner_upload import ScannerUpload
from app.schemas.privacy import PrivacyApprovalRead, PrivacyApprovalRequest, PrivacyDetectRequest, PrivacyEventRead
from app.services.privacy_service import require_redaction_service

router = APIRouter(prefix="/api/privacy", tags=["privacy"])
_SUPPORTED_INFORMATION_TYPES = {
    "name", "phone_number", "address", "invoice_number", "gstin",
    "payment_reference", "qr_code", "barcode",
}


@router.post("/detect")
async def detect_private_information(
    request: PrivacyDetectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await session.scalar(select(Bill.id).where(Bill.id == request.bill_id, Bill.user_id == user.id, Bill.is_deleted.is_(False)))
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    require_redaction_service()


@router.get("/{bill_id}/detections", response_model=list[PrivacyEventRead])
async def list_privacy_detections(
    bill_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await session.scalar(select(Bill.id).where(Bill.id == bill_id, Bill.user_id == user.id, Bill.is_deleted.is_(False)))
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    result = await session.execute(
        select(PrivacyEvent).where(PrivacyEvent.bill_id == bill_id, PrivacyEvent.user_id == user.id).order_by(PrivacyEvent.created_at)
    )
    return list(result.scalars())


@router.post("/{bill_id}/approve", response_model=PrivacyApprovalRead)
async def approve_privacy_review(
    bill_id: uuid.UUID,
    request: PrivacyApprovalRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await session.scalar(
        select(Bill).where(Bill.id == bill_id, Bill.user_id == user.id, Bill.is_deleted.is_(False)).with_for_update()
    )
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    upload = await session.scalar(
        select(ScannerUpload).where(
            ScannerUpload.bill_id == bill.id,
            ScannerUpload.user_id == user.id,
            ScannerUpload.status == "attached",
        )
    )
    if request.retain_original_consent and upload is None:
        raise HTTPException(status_code=409, detail="There is no bill image to retain.")
    if request.retain_original_consent:
        bill.original_image_path = upload.storage_path
        upload.status = "original_retained_with_consent"
    bill.review_status = "approved_pending_redaction"
    session.add(
        PrivacyEvent(
            user_id=user.id,
            bill_id=bill.id,
            detected_information_type="user_review",
            redaction_status="approved",
        )
    )
    await session.commit()
    return PrivacyApprovalRead(
        bill_id=bill.id,
        review_status=bill.review_status,
        original_retention_consented=bool(request.retain_original_consent and upload),
    )


@router.post("/{bill_id}/redact")
async def redact_bill_image(
    bill_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    bill = await session.scalar(select(Bill.id).where(Bill.id == bill_id, Bill.user_id == user.id, Bill.is_deleted.is_(False)))
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    require_redaction_service()
