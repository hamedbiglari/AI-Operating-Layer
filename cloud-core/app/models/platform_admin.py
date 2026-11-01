"""
Platform administrators (Step 14B): users who may read across organizations through /api/v1/admin.

Deliberately NOT a tenant role. UserRole and ADMIN_ROLES stay organization-scoped, so no tenant route,
service or check can mistake this for "admin of this organization". A row here is the only grant; it is
created by an operator in the database (there is no API that grants it) and goes with the user.
organization_id is the user's own organization (kept, like on every table, so each row belongs to one tenant
and is deleted with it); it does not limit what the admin may read.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class PlatformAdmin(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "platform_admins"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_platform_admins_user_id"),
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_platform_admins_user_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
