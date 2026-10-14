"""
Keyword Trace (REQ-KW-004) — explicit, queryable chain from a keyword
to its published content.

Rather than storing one giant JSON blob, each row records the IDs of the
artifacts produced at each stage of the pipeline.  Nullable FKs denote
stages that have not occurred yet (an incomplete but honest chain).

Chain:
  keyword_id
    → research_task_id   (phase 5 — source discovery)
    → source_id          (phase 3)
    → evidence_id        (phase 4)
    → claim_id           (phase 4)
    → knowledge_object_id (phase 2)
    → knowledge_version_id (phase 2)
    → published_target   (string URL/path — no FK; outside Core)

All FKs are nullable because a keyword may enter the chain at any stage.
The `stage` column records the highest stage reached.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

STAGE_KEYWORD = "keyword"
STAGE_RESEARCH = "research_task"
STAGE_SOURCE = "source"
STAGE_EVIDENCE = "evidence"
STAGE_CLAIM = "claim"
STAGE_KNOWLEDGE = "knowledge_object"
STAGE_VERSION = "knowledge_version"
STAGE_PUBLISHED = "published"

ALL_STAGES = [STAGE_KEYWORD, STAGE_RESEARCH, STAGE_SOURCE, STAGE_EVIDENCE,
              STAGE_CLAIM, STAGE_KNOWLEDGE, STAGE_VERSION, STAGE_PUBLISHED]


class KeywordTrace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per keyword × pipeline-run.  Multiple runs of the same keyword
    produce multiple trace rows (each with the same keyword_id but different
    research_task_ids / source_ids / …)."""

    __tablename__ = "keyword_traces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_keywords.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default=STAGE_KEYWORD)

    # Stage 1 → research task
    research_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_tasks.id", ondelete="SET NULL"), nullable=True
    )
    # Stage 2 → source
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    # Stage 3 → evidence
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True
    )
    # Stage 4 → claim
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), nullable=True
    )
    # Stage 5 → knowledge object
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"), nullable=True
    )
    # Stage 6 → knowledge version (stored as int on the KO)
    knowledge_version_id: Mapped[int | None] = mapped_column(nullable=True)
    # Stage 7 → published target (URL/path outside Core — no FK)
    published_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Notes about this trace leg
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # A keyword+task combination must be unique (prevents duplicate traces per run)
        UniqueConstraint("organization_id", "keyword_id", "research_task_id",
                         name="uq_keyword_trace_keyword_task"),
    )
