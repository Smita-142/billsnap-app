import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ExtractionResult(Base):
    __tablename__ = "extraction_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_name: Mapped[str | None] = mapped_column(String(200))
    extracted_date: Mapped[date | None] = mapped_column(Date)
    extracted_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    merchant_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    date_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    amount_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    category_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    model_name: Mapped[str | None] = mapped_column(String(120))
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bill: Mapped["Bill"] = relationship(back_populates="extraction_results")
