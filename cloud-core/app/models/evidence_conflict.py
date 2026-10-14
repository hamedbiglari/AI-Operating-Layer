"""
A disagreement between two reviewed findings about the same claim (ADR-110).

The system never silently prefers one of them. It records both, the comparison a person needs in order to
judge (population, intervention, dose, duration, outcome, design, sample size, date), and the state of the
review. `resolved` and `unresolvable` require a written reason — a database constraint enforces that.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONFLICT_STATES = ("unreviewed", "under_review", "partially_resolved", "resolved", "unresolvable")
COMPARISON_FIELDS = ("population", "intervention", "dose", "duration", "outcome", "endpoint",
                     "study_design", "sample_size", "publication_date")


class EvidenceConflict(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_conflicts"
    __table_args__ = (
        CheckConstraint(f"status IN ({', '.join(repr(s) for s in CONFLICT_STATES)})", name="status"),
        CheckConstraint("supporting_evidence_id <> contradicting_evidence_id", name="two_different_findings"),
        CheckConstraint("status IN ('unreviewed', 'under_review') OR resolution_note IS NOT NULL",
                        name="a_decision_needs_a_reason"),
        UniqueConstraint("organization_id", "claim_id", "supporting_evidence_id", "contradicting_evidence_id",
                         name="uq_evidence_conflict"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"))
    supporting_evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    contradicting_evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unreviewed")
    comparison: Mapped[dict | None] = mapped_column(JSON)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
