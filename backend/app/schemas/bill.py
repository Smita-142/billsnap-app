import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BillItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_name: str = Field(min_length=1, max_length=240)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    total_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class BillCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    merchant_name: str = Field(min_length=1, max_length=200)
    bill_date: date
    total_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    category_id: uuid.UUID | None = None
    payment_method: str | None = Field(default=None, max_length=60)
    bill_type: Literal["receipt", "invoice", "other"] = "receipt"
    upload_id: uuid.UUID | None = None
    items: list[BillItemCreate] = Field(default_factory=list, max_length=500)


class BillUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    merchant_name: str | None = Field(default=None, min_length=1, max_length=200)
    bill_date: date | None = None
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    category_id: uuid.UUID | None = None
    payment_method: str | None = Field(default=None, max_length=60)
    bill_type: Literal["receipt", "invoice", "other"] | None = None

    @model_validator(mode="after")
    def reject_explicit_null_for_required_fields(self):
        for field in ("merchant_name", "bill_date", "total_amount", "currency", "bill_type"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class BillItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


class BillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    merchant_name: str
    bill_date: date
    total_amount: Decimal
    currency: str
    category_id: uuid.UUID | None
    payment_method: str | None
    bill_type: str
    review_status: str
    overall_confidence: Decimal | None
    created_at: datetime
    updated_at: datetime
    items: list[BillItemRead]


class BillPage(BaseModel):
    items: list[BillRead]
    page: int
    page_size: int
    total: int
