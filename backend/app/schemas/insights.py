from decimal import Decimal

from pydantic import BaseModel


class SpendingSummary(BaseModel):
    total_amount: Decimal
    bill_count: int
    average_amount: Decimal
    highest_spending_category: str | None
    currency: str
