"""
Pending passwordless organization sign-up (ADR-106).

A sign-up request stores only an HMAC of the 6-digit code — never the code itself — together with
the organization and owner details. Nothing is created in `organizations` / `users` until the code
is verified, so an unverified request cannot occupy an organization name or an email address.
One-time use is enforced by `consumed_at`; brute force by `attempts` and the IP/email throttle.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SignupCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Not tenant-scoped on purpose: no tenant exists yet. It creates one."""
    __tablename__ = "signup_codes"
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_ip: Mapped[str | None] = mapped_column(String(64))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))   # set when it succeeds
