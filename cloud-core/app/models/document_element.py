"""
`document_elements` — the persisted Canonical Document Representation (prompt v4.0 §6, §9; ADR-122).

One row per CDR element, belonging to exactly one `document_conversions` row (one extraction attempt by
one provider). Because elements hang off the conversion and not directly off the document, every
candidate extraction keeps its own complete reading of the document: a reprocess with a newer provider
adds a new set of elements beside the old ones instead of overwriting them (§12, §56). Which set is
authoritative is `document_conversions.is_current`.

`(document_id, page, bbox)` is the location a claim can point at (§9): evidence carries
`document_element_id`, so "show every claim derived from page 37" is a join, not a text search.
"""
import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentElement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_elements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "organization_id"], ["documents.id", "documents.organization_id"],
            name="fk_document_elements_document_organization", ondelete="CASCADE",
        ),
        UniqueConstraint("conversion_id", "reading_order", name="uq_document_elements_order"),
        Index("ix_document_elements_doc_page", "document_id", "page"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_in_range"),
        CheckConstraint("page IS NULL OR page >= 1", name="page_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    conversion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_conversions.id", ondelete="CASCADE"), nullable=False, index=True)

    element_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)        # NULL: not a paginated source
    block_id: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_block_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)            # exactly as read
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # NFC + ligatures, never NFKC
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    script: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(3), nullable=True)

    # [x0, y0, x1, y1] in the page's own units (PDF points; image pixels for images). NULL = unknown.
    bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    # extraction confidence for THIS element — never evidence quality
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
