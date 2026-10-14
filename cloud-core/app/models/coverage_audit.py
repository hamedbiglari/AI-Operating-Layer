"""
Coverage Audit (ADR-115, prompt v3.0 §17–§23).

A persisted, versioned, recalculable record of how complete a topic's or a category's knowledge is —
kept in SIX separate dimensions, because collapsing them into one number is exactly the lie the owner
asked us not to tell. A topic can have every section present (section coverage 100%) and almost no
evidence behind them (evidence coverage 12%).

Nothing here is a new source of truth: every figure is counted from tables that already exist —
`sources`, `documents`, `evidence`, `claims`, `knowledge_gaps`, `evidence_conflicts`,
`knowledge_sections`. The audit is a cache with provenance, not a second knowledge base.

§78: a failed run NEVER overwrites a good one. It is stored as its own row with `status='failed'`,
and the previous successful row stays readable and is what the Dashboard shows, marked stale.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCOPES = ("topic", "category", "organization")
AUDIT_STATUSES = ("succeeded", "failed", "running")
# §19 — the six dimensions, never collapsed into one figure
DIMENSIONS = ("source", "processing", "knowledge", "evidence", "section", "publication")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class CoverageAudit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One run of the audit over one scope. Rows are append-only in practice: a new run is a new row,
    so the history of how coverage moved stays auditable (§24)."""
    __tablename__ = "coverage_audits"
    __table_args__ = (
        CheckConstraint(f"scope IN ({_q(SCOPES)})", name="scope"),
        CheckConstraint(f"status IN ({_q(AUDIT_STATUSES)})", name="status"),
        CheckConstraint("status <> 'failed' OR failure_reason IS NOT NULL", name="a_failure_needs_a_reason"),
        CheckConstraint("(scope = 'topic') = (knowledge_object_id IS NOT NULL)", name="topic_scope_needs_a_topic"),
        CheckConstraint("(scope = 'category') = (category_id IS NOT NULL)", name="category_scope_needs_a_category"),
        CheckConstraint("audit_version >= 1", name="audit_version_positive"),
        UniqueConstraint("organization_id", "scope", "knowledge_object_id", "category_id", "audit_version",
                         name="uq_coverage_audit_version"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    audit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    knowledge_version: Mapped[int | None] = mapped_column(Integer)        # the KO version this ran against
    schema_version: Mapped[int | None] = mapped_column(Integer)           # the category schema it ran against
    trigger: Mapped[str | None] = mapped_column(String(40))               # manual | source_change | research | schedule
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # the six dimensions, each a self-describing block: counts + what is missing + how it was measured
    dimensions: Mapped[dict | None] = mapped_column(JSON)
    # cross-topic findings for a category run (§22) — never a sum of topic rows
    cross_topic: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
