import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PrivacyEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_id: uuid.UUID
    detected_information_type: str
    redaction_status: str
    created_at: datetime


class PrivacyDetectRequest(BaseModel):
    bill_id: uuid.UUID


class PrivacyApprovalRequest(BaseModel):
    retain_original_consent: bool = False


class PrivacyApprovalRead(BaseModel):
    bill_id: uuid.UUID
    review_status: str
    original_retention_consented: bool
    sanitized_image_created: bool = False
    external_processing_started: bool = False
