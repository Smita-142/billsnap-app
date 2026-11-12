import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        Index("ix_bills_user_date", "user_id", "bill_date"),
        Index("ix_bills_user_merchant", "user_id", "merchant_name"),
        Index("ix_bills_user_category", "user_id", "category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    payment_method: Mapped[str | None] = mapped_column(String(60))
    original_image_path: Mapped[str | None] = mapped_column(String(512))
    sanitized_image_path: Mapped[str | None] = mapped_column(String(512))
    bill_type: Mapped[str] = mapped_column(String(32), nullable=False, default="receipt")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    overall_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    category: Mapped["Category | None"] = relationship(back_populates="bills")
    items: Mapped[list["BillItem"]] = relationship(back_populates="bill", cascade="all, delete-orphan", passive_deletes=True)
    extraction_results: Mapped[list["ExtractionResult"]] = relationship(back_populates="bill", cascade="all, delete-orphan", passive_deletes=True)
    privacy_events: Mapped[list["PrivacyEvent"]] = relationship(back_populates="bill", cascade="all, delete-orphan", passive_deletes=True)
