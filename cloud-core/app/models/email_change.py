"""
Pending sign-in email changes (V5-self-email-verification).

A user's sign-in address changes only after a 6-digit code sent to the NEW address is entered: a mistyped address
can no longer lock the user out, and a stolen session cannot move the account to an address the attacker controls
without also reading that inbox. Only a keyed hash of the code is stored (HMAC-SHA256 with SECRET_KEY, bound to the
user and the new address). One row per request; a newer request supersedes the older ones (consumed_at is set).
"""
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailChangeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_change_requests"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_email_change_requests_user_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    new_email: Mapped[str] = mapped_column(String(320), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
