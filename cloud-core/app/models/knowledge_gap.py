"""
KnowledgeGap: tracks a specific, actionable deficiency in a Knowledge
Object (master spec section 20) - e.g. "no clinical evidence found yet
for this claim" or "missing an authoritative source for origin". These
are what the future Research Engine (Phase 5) consumes to decide what
to look for next; Phase 2 only implements the gap record itself and its
manual lifecycle (open -> in_progress -> resolved/dismissed).
"""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GapPriority, GapRecommendedAction, GapStatus, GapType


class KnowledgeGap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_gaps"

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
    gap_type: Mapped[GapType] = mapped_column(
        SAEnum(GapType, name="gap_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[GapPriority] = mapped_column(
        SAEnum(GapPriority, name="gap_priority", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=GapPriority.MEDIUM,
        server_default=GapPriority.MEDIUM.value,
    )
    status: Mapped[GapStatus] = mapped_column(
        SAEnum(GapStatus, name="gap_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=GapStatus.OPEN,
        server_default=GapStatus.OPEN.value,
    )
    recommended_action: Mapped[GapRecommendedAction | None] = mapped_column(
        SAEnum(GapRecommendedAction, name="gap_recommended_action", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )

    knowledge_object: Mapped["KnowledgeObject"] = relationship(back_populates="gaps")  # noqa: F821

    @property
    def knowledge_object_name(self) -> str:
        """The object's name for KnowledgeGapRead, so a list of gaps needs no
        call per row to name its objects (Rule 17). Lists load it with the
        gaps in one joined query."""
        return self.knowledge_object.canonical_name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeGap id={self.id} type={self.gap_type.value} status={self.status.value}>"
