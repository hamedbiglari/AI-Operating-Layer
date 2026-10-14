"""
KnowledgeVersion: an immutable snapshot of a Knowledge Object at a point
in time (master spec section 21: "Knowledge must be versioned ... diff,
audit, rollback, review, publishing status").

Design decision beyond the literal field list: section 21 does not list
organization_id, but section 8 makes organization_id mandatory on EVERY
tenant-owned table without exception. It is added here, denormalized
from the parent knowledge_object, so tenant-scoped queries and the
cross-tenant isolation guard (get_tenant_scoped_or_404) work identically
to every other resource in the system without an extra join.

Rows are written by the service layer (never mutated afterward), one
per meaningful change to a Knowledge Object - see
app/services/knowledge_service.py.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint("knowledge_object_id", "version", name="uq_knowledge_versions_object_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full serialized state of the Knowledge Object at this version -
    # enables diff (compare two snapshots) and rollback (re-apply an
    # older snapshot's fields) without needing a separate diff-storage
    # scheme.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    knowledge_object: Mapped["KnowledgeObject"] = relationship(back_populates="versions")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeVersion knowledge_object_id={self.knowledge_object_id} version={self.version}>"
