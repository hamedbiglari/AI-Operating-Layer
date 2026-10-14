"""
Publication layer and sentence-level Vancouver citation (ADR-116, prompt v3.0 §33–§67).

The order of these tables is the whole point. A sentence is not written and then annotated: a
`PublicationSentence` is created FROM a knowledge unit that already carries its source set, and the
resolver then assigns numbers. There is no path in this schema that lets prose exist without the
sources that produced it.

    Publication ──< PublicationSection ──< PublicationSentence ──< SentenceSource
                                                                        │
    PublicationReference (the Vancouver number) ────────────────────────┘

`SentenceSource` is the evidentiary link: it names the claim and evidence that justify this sentence for
this source, so "does the source actually support the claim" is answerable per sentence (§48, §60).
`PublicationReference` holds one row per canonical source per publication version — the number map.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PUBLICATION_STATUSES = ("draft", "resolving", "resolved", "published", "superseded", "failed")
# §62 — a sentence that states a fact is not the same as one that reasons about facts
SENTENCE_KINDS = ("factual", "inference", "interpretation", "hypothesis", "narrative", "heading")
# which of those must carry a citation (§59)
CITATION_REQUIRED_KINDS = ("factual", "inference", "interpretation")
SUPPORT_STATES = ("supports", "partially_supports", "background_only", "unverified")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generated version of a topic's knowledge. Numbering is global within one publication (§37)."""
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint(f"status IN ({_q(PUBLICATION_STATUSES)})", name="status"),
        CheckConstraint("status <> 'failed' OR failure_reason IS NOT NULL", name="a_failure_needs_a_reason"),
        CheckConstraint("publication_version >= 1", name="version_positive"),
        UniqueConstraint("organization_id", "knowledge_object_id", "publication_version",
                         name="uq_publication_version"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    knowledge_version: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class PublicationSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publication_sections"
    __table_args__ = (
        UniqueConstraint("publication_id", "position", name="uq_publication_section_position"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)
    section_key: Mapped[str | None] = mapped_column(String(100))          # ties back to the knowledge section
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class PublicationSentence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One sentence in document order. `citation_numbers` is written by the resolver, never by hand."""
    __tablename__ = "publication_sentences"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_q(SENTENCE_KINDS)})", name="kind"),
        CheckConstraint("position >= 0", name="position_positive"),
        # §61/§87 — a sentence that needs a citation may not be marked resolved with none
        CheckConstraint("NOT resolved OR kind NOT IN ('factual', 'inference', 'interpretation') "
                        "OR evidence_unavailable OR citation_numbers IS NOT NULL",
                        name="a_factual_sentence_needs_a_citation"),
        UniqueConstraint("publication_id", "position", name="uq_publication_sentence_position"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("publication_sections.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)        # global document order
    paragraph: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="factual")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_unit_claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # §61 — the honest alternative to inventing a citation
    evidence_unavailable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    citation_numbers: Mapped[list | None] = mapped_column(JSON)          # e.g. [1, 3, 5, 8]
    citation_text: Mapped[str | None] = mapped_column(String(300))       # e.g. "(1,3,5,8)"


class SentenceSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which source supports this sentence, and through which claim and evidence (§43, §48)."""
    __tablename__ = "sentence_sources"
    __table_args__ = (
        CheckConstraint(f"support IN ({_q(SUPPORT_STATES)})", name="support"),
        UniqueConstraint("publication_sentence_id", "source_id", name="uq_sentence_source"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_sentence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publication_sentences.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"))
    support: Mapped[str] = mapped_column(String(30), nullable=False, default="supports")
    directness: Mapped[str | None] = mapped_column(String(20))           # carried through from the evidence
    note: Mapped[str | None] = mapped_column(Text)


class PublicationReference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The number map for one publication: one row per canonical source, numbered by first appearance.

    Two unique constraints do the work the prompt insists on: a number cannot belong to two sources
    (§59), and a source cannot hold two numbers (§39, §57)."""
    __tablename__ = "publication_references"
    __table_args__ = (
        CheckConstraint("reference_number >= 1", name="number_positive"),
        UniqueConstraint("publication_id", "reference_number", name="uq_reference_number_per_publication"),
        UniqueConstraint("publication_id", "source_id", name="uq_source_once_per_publication"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    reference_number: Mapped[int] = mapped_column(Integer, nullable=False)
    first_sentence_position: Mapped[int | None] = mapped_column(Integer)
    formatted: Mapped[str | None] = mapped_column(Text)                  # the Vancouver string
    source_kind: Mapped[str | None] = mapped_column(String(50))
    # §63/§64 — what the reader must be told about this source
    is_user_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_note: Mapped[str | None] = mapped_column(String(200))         # e.g. "abstract only"
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)     # exactly the stored fields used
