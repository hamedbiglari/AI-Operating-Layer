"""
Research query sets (§12) and evidence-completion tasks (§16) — ADR-111.

A `ResearchQuerySet` is a saved, editable set of keywords and terms for one knowledge object: the question a
merchant keeps asking, kept so it can be re-run and compared over time.

An `EvidenceCompletionTask` names what is still missing for a claim or a gap — which route and which
directness would satisfy it — and stays open until a specific piece of evidence satisfies it, or a person
writes down why it cannot be satisfied. Database constraints enforce both of those.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

COMPLETION_STATES = ("open", "searching", "awaiting_review", "satisfied", "blocked", "abandoned")


class ResearchQuerySet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Not to be confused with `QueryCluster` (Phase 13), which groups observed demand queries."""
    __tablename__ = "research_query_sets"
    __table_args__ = (
        CheckConstraint("mode IN ('single', 'multi', 'exact', 'boolean', 'agent')", name="mode"),
        UniqueConstraint("organization_id", "knowledge_object_id", "name", name="uq_research_query_set_name"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    keyword_ids: Mapped[list | None] = mapped_column(JSON)
    extra_terms: Mapped[list | None] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    boolean_query: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EvidenceCompletionTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_completion_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN ({', '.join(repr(s) for s in COMPLETION_STATES)})", name="status"),
        CheckConstraint("required_directness IS NULL OR required_directness IN ('direct', 'indirect')", name="required_directness"),
        CheckConstraint("status <> 'satisfied' OR satisfied_by_evidence_id IS NOT NULL", name="satisfied_needs_evidence"),
        CheckConstraint("status NOT IN ('blocked', 'abandoned') OR outcome_note IS NOT NULL", name="a_dead_end_needs_a_reason"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"))
    knowledge_gap_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_gaps.id", ondelete="SET NULL"))
    research_question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_questions.id", ondelete="SET NULL"))
    what_is_missing: Mapped[str] = mapped_column(Text, nullable=False)
    required_route: Mapped[str | None] = mapped_column(String(30))
    required_directness: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    satisfied_by_evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"))
    outcome_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
