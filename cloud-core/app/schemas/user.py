"""Pydantic contracts for User."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole, UserStatus


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Used by an existing admin/owner to add a teammate to their org."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    status: UserStatus | None = None


class UserSelfUpdate(BaseModel):
    """PATCH /users/me: the signed-in user's own name. Role and status stay admin-only, and the sign-in email changes
    only through the confirmed flow (POST /users/me/email-change-request, then -verify; V5-self-email-verification)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _no_direct_email(cls, v: str | None) -> None:
        if v is not None:
            raise ValueError("The sign-in email changes only after confirmation: use POST /users/me/email-change-request.")
        return None


class EmailChangeRequestIn(BaseModel):
    new_email: EmailStr


class EmailChangeVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern="^[0-9]{6}$")
