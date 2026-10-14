"""
Category schema, sections and the Master Topic Matrix (ADR-114, §11–§16 of the v3.0 prompt).

Why a Category table and not `knowledge_objects.object_type`: the matrix needs a *schema* per category
(the sections a plant has are not the sections a smartphone has), a per-topic status row for every section
including the ones that do not apply, and a schema version so a recomputed matrix stays auditable. A
free-text column cannot carry any of that. `object_type` is untouched and keeps working as before; a
Knowledge Object without a category behaves exactly as it did.

    Category ──< SectionDefinition          the schema: which sections this category expects
        │                 │
        └──< KnowledgeObject (topic)        existing table, gains a nullable category_id
                          │
                     KnowledgeSection       one row per topic × section: its status and its evidence
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# §14 — every state a cell can honestly be in. Never conveyed by colour alone in the UI.
SECTION_STATUSES = (
    "documented",          # written and sourced
    "verified",            # a person checked it against the evidence
    "partial",             # some of it is sourced, some is not
    "needs_research",      # the section applies and nothing has been found yet
    "field_research",      # only field observation can answer it
    "experiment_required", # only an experiment can answer it
    "user_input",          # awaiting something only the owner knows
    "new",                 # discovered by research, not yet reviewed
    "conflicting",         # sources disagree
    "outdated",            # the evidence behind it has moved on
    "processing",          # a job is working on it now
    "no_evidence_found",   # searched honestly, found nothing
    "not_applicable",      # this section does not apply to this topic
    "error",               # the last attempt failed; the previous state is kept
)
TERMINAL_UNRESOLVED = ("no_evidence_found", "not_applicable")
ORIGINS = ("category_schema", "discovered", "user_added")
PROPAGATION_STATES = ("pending", "evaluated", "skipped")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A family of topics that share a knowledge schema: medicinal plants, smartphones, detergents…"""
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_categories_slug"),
        CheckConstraint("schema_version >= 1", name="schema_version_positive"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"))


class SectionDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row of the Master Topic Matrix: a knowledge dimension this category expects its topics to cover."""
    __tablename__ = "section_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "category_id", "key", name="uq_section_definition_key"),
        CheckConstraint(f"origin IN ({_q(ORIGINS)})", name="origin"),
        CheckConstraint("position >= 0", name="position_positive"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)          # stable identifier, e.g. "composition"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="category_schema")
    # §12: a discovered section records where it came from and waits for review
    discovered_from_topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"))
    discovered_evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class KnowledgeSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One cell of the matrix: what this topic has for this section, and how we know.

    The cell never holds prose. It holds status and the links to the claims and evidence that justify
    that status, so the matrix can never drift from the knowledge it claims to describe."""
    __tablename__ = "knowledge_sections"
    __table_args__ = (
        UniqueConstraint("organization_id", "knowledge_object_id", "section_key", name="uq_knowledge_section"),
        CheckConstraint(f"status IN ({_q(SECTION_STATUSES)})", name="status"),
        CheckConstraint(f"origin IN ({_q(ORIGINS)})", name="origin"),
        # §78: a failed recalculation must not erase what was last known
        CheckConstraint("status <> 'error' OR last_good_status IS NOT NULL", name="error_keeps_last_good"),
        CheckConstraint("status NOT IN ('not_applicable', 'no_evidence_found') OR rationale IS NOT NULL",
                        name="a_closed_cell_needs_a_reason"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    section_definition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("section_definitions.id", ondelete="SET NULL"))
    section_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="needs_research")
    last_good_status: Mapped[str | None] = mapped_column(String(30))
    rationale: Mapped[str | None] = mapped_column(Text)                    # why it is closed, or why it failed
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="category_schema")
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    research_question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_questions.id", ondelete="SET NULL"))
    knowledge_version: Mapped[int | None] = mapped_column(Integer)
    last_research_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_audited_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)


class SectionPropagation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """§16 — a section discovered on one topic has to be *considered* for its siblings, not copied to them.

    One row per sibling topic, created pending. Nothing is written into that topic's knowledge until a
    person or a research run decides. This is what stops a discovery on one plant from fabricating a
    section on another."""
    __tablename__ = "section_propagations"
    __table_args__ = (
        UniqueConstraint("organization_id", "section_definition_id", "knowledge_object_id", name="uq_section_propagation"),
        CheckConstraint(f"state IN ({_q(PROPAGATION_STATES)})", name="state"),
        CheckConstraint("state <> 'skipped' OR note IS NOT NULL", name="skipping_needs_a_reason"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    section_definition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("section_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    resulting_status: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
