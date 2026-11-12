import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, max_length=160)
    preferred_language: str | None = Field(default=None, min_length=2, max_length=16)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")

    @model_validator(mode="after")
    def reject_null_preferences(self):
        for field in ("preferred_language", "preferred_currency"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    email: str | None
    preferred_language: str
    preferred_currency: str
    created_at: datetime
    updated_at: datetime


class AuthUserRead(BaseModel):
    id: uuid.UUID
    email: str | None
