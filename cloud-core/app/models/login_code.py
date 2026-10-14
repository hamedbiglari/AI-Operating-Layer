"""
Email one-time login code (owner requirement recorded in Phase 13 addendum 9,
Phase 14 prompt §33; owner phases 1 / 13).

Rules (owner's words, as recorded): a 6-digit code is emailed; it can be
re-sent only after 5 minutes; 3 wrong codes lock the address for 1 hour;
3 more wrong codes lock it for 24 hours and the user is told to contact
support. Code lifetime was not specified by the owner; it is set equal to
the resend window (5 minutes) — recorded as an INFERENCE, configurable.

Only a keyed hash of the code is stored (HMAC-SHA256 with SECRET_KEY), never
the code itself. Rows are per user; no tenant data is readable before the
code is verified.
"""
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LoginCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "login_codes"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_login_codes_user_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class LoginCodeThrottle(TimestampMixin, Base):
    """One row per user: resend window and the two-step lockout."""

    __tablename__ = "login_code_throttles"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_login_code_throttles_user_org"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resend_available_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # 0 = never locked, 1 = served the 1-hour lock, 2 = 24-hour lock (contact support)
    lock_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
