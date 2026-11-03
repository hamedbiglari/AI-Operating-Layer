"""
User: belongs to exactly one Organization (master spec section 10 fields).

Deactivation is modeled via `status` transitioning to DEACTIVATED rather
than deleting the row, preserving audit/history integrity.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import TIMESTAMP, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, UserStatus


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Phase 17: composite tenant-FK target for ai_executions (ADR-037).
        UniqueConstraint("id", "organization_id", name="uq_users_id_organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.VIEWER,
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    # NULL for a passwordless owner created by email-code sign-up (ADR-106); such a user signs in with a code.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # When the user agreed to occasional product updates at sign-up; null = no consent (V5-signup-marketing-optin).
    marketing_optin_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Soft delete for the admin trash (migration 0058, V5-admin-trash): a deleted user cannot sign in and leaves the
    # lists until a platform admin restores or purges them. deleted_by_id = the platform admin who deleted them.
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True, index=True)
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", name="fk_users_deleted_by_id_users"), nullable=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r} org={self.organization_id}>"
