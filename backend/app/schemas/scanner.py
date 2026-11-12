import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScannerUploadRead(BaseModel):
    upload_id: uuid.UUID
    status: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    temporary: bool = True


class OCRFieldRead(BaseModel):
    value: str | Decimal | None
    confidence: float = Field(ge=0, le=1)
    confidence_level: Literal["high", "medium", "low"]
    uncertain: bool
    reason: str | None = None


class OCRLineRead(BaseModel):
    text: str
    bbox: list[list[float]]
    confidence: float = Field(ge=0, le=1)


DocumentType = Literal[
    "bill",
    "receipt",
    "invoice",
    "identity_document",
    "bank_statement",
    "general_document",
    "normal_photograph",
    "unknown",
    "non_bill",
    "uncertain",
]


class OCRClassificationRead(BaseModel):
    label: DocumentType | str
    status: DocumentType | str
    document_type: str | None = None
    message: str
    confidence: float = Field(ge=0, le=1)
    confidence_basis: str
    reasons: list[str]
    warnings: list[str]
    should_continue_ocr: bool
    should_continue_field_extraction: bool
    evidence: dict[str, Any]


class OCRVariantRead(BaseModel):
    text: str
    lines: list[OCRLineRead]
    fields: dict[str, OCRFieldRead]
    extraction_warnings: list[str]
    classification: OCRClassificationRead
    comparison_score: float
    ocr_confidence: float = Field(ge=0, le=1)
    processing_time_ms: float = Field(ge=0)


class OCRComparisonsRead(BaseModel):
    raw: OCRVariantRead
    preprocessed: OCRVariantRead
    preprocessing_steps: list[str]


class TimingBreakdownRead(BaseModel):
    image_loading_ms: float = 0.0
    preprocessing_ms: float = 0.0
    ocr_detection_recognition_ms: float = 0.0
    text_post_processing_ms: float = 0.0
    field_extraction_ms: float = 0.0
    document_classification_ms: float = 0.0
    total_processing_ms: float = 0.0


class OCRRead(BaseModel):
    engine: Literal["PaddleOCR", "EasyOCR"] = "PaddleOCR"
    languages: list[str]
    text: str
    bounding_boxes: list[OCRLineRead]
    fields: dict[str, OCRFieldRead]
    classification: OCRClassificationRead
    selected_variant: Literal["raw", "preprocessed"]
    comparisons: OCRComparisonsRead
    warnings: list[str]
    processing_time_ms: float = Field(ge=0)
    timing_breakdown: TimingBreakdownRead | None = None

