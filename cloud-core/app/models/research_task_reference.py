"""
ResearchTaskReference: one entry in a ResearchTask's provenance trail —
"what sources/documents were involved, what evidence/source records
were discovered or referenced" (section 10). A small, Phase-5-scoped
polymorphic link (see ResearchReferenceType's docstring for why this
is a new enum/table rather than extending Relationship/GraphNodeType),
resolved and tenant-checked the same way relationship_service.py
resolves Relationship's subject/object.

Deliberately created_at-only, no TimestampMixin: these rows are an
immutable execution-log trail, never edited in place — same reasoning
DocumentChunk already documents for its own created_at-only choice.
Section 13 is explicit that this must not duplicate the referenced
row's own data ("Do not store the same source data again inside
ResearchTask.result") — this table stores only the pointer
(reference_type + reference_id) and its role, nothing else.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ResearchReferenceRole, ResearchReferenceType


class ResearchTaskReference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_task_references"

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_type: Mapped[ResearchReferenceType] = mapped_column(
        SAEnum(ResearchReferenceType, name="research_reference_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # No DB-level FK — this points at one of several possible tables
    # depending on reference_type, the same polymorphic-pointer
    # technique Relationship.subject_id/object_id already uses.
    # Resolved and tenant-checked by research_task_service.py before
    # insert, never trusted as-is.
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[ResearchReferenceRole] = mapped_column(
        SAEnum(ResearchReferenceRole, name="research_reference_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ResearchReferenceRole.OUTPUT,
        server_default=ResearchReferenceRole.OUTPUT.value,
    )

    research_task: Mapped["ResearchTask"] = relationship(back_populates="references")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ResearchTaskReference task_id={self.research_task_id} "
            f"{self.role.value}:{self.reference_type.value}:{self.reference_id}>"
        )
