"""
Audit log: records important mutations for traceability (master spec
section 42, and listed explicitly under MVP INFRASTRUCTURE scope in
section 54). old_value/new_value are stored as JSON snapshots — nullable
because not every action has a meaningful before/after (e.g. login).

This is a minimal, generic write-path for Phase 1 (organizations, users,
sites, auth events). Later phases add audit writes for their own
mutations using the same table and `record_audit_log` helper.
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # created_at from TimestampMixin serves as the audit timestamp;
    # updated_at is unused for this append-only table but kept for
    # consistency with the rest of the schema.

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog action={self.action!r} resource={self.resource_type}:{self.resource_id}>"
