"""
Document Intelligence persistence (Phase 3 completion; ADR-065).

Three tables, because three different things need to be traceable:

  `document_conversions`  what the converter did, and with what version
  `document_tables`       structured tables, recoverable without re-parsing
  `document_assets`       images/figures, including ones we could NOT read

`document_assets` is the one worth explaining. Recording an image we failed
to interpret looks like recording a failure - and it is. But the
alternative is an artifact that silently implies the page had no figure,
which is precisely the MarkItDown behaviour this whole layer exists to
correct.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Enum as SAEnum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    DocumentAssetStatus,
    DocumentConversionStatus,
    DocumentExtractionLevel,
    DocumentOcrStatus,
)


def _enum(enum_cls, name):
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class DocumentConversion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One normalization attempt, with full provenance (§14).

    A row exists even when conversion FAILED. A failed conversion that
    leaves no trace is indistinguishable from a file nobody uploaded."""

    __tablename__ = "document_conversions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "organization_id"], ["documents.id", "documents.organization_id"],
            name="fk_document_conversions_document_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Hash of the ORIGINAL BYTES. Distinct from Document.content_hash, which
    # hashes extracted text and therefore cannot detect a re-upload of the
    # same binary or two different files yielding identical text.
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    converter_name: Mapped[str] = mapped_column(String(80), nullable=False)
    converter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    conversion_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    conversion_status: Mapped[DocumentConversionStatus] = mapped_column(
        _enum(DocumentConversionStatus, "document_conversion_status"),
        nullable=False, default=DocumentConversionStatus.PENDING,
        server_default=DocumentConversionStatus.PENDING.value, index=True,
    )
    conversion_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    conversion_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    extraction_level: Mapped[DocumentExtractionLevel] = mapped_column(
        SAEnum(DocumentExtractionLevel, name="document_extraction_level",
               values_callable=lambda e: [str(m.value) for m in e]),
        nullable=False, default=DocumentExtractionLevel.NORMALIZE,
        server_default="1",
    )

    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ocr_block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    ocr_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # NULL means no vision model was used. There is no code path that sets
    # it today (Level 4 is not built); the column exists so that when one
    # is added, model-derived content is distinguishable from the start.
    vision_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    warnings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class DocumentTable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A table kept as STRUCTURE, not only as Markdown text (§7).

    Markdown is lossy for high-value tabular data: once flattened to a
    string, a numeric column cannot be queried. Both representations are
    stored - `rows` for machines, `markdown` for the artifact."""

    __tablename__ = "document_tables"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "organization_id"], ["documents.id", "documents.organization_id"],
            name="fk_document_tables_document_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    headers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    # Which pdfplumber strategy produced it. `lines` is unambiguous;
    # `text` is inferred from whitespace and therefore less certain - a
    # consumer weighting this data needs to know which.
    extraction_strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class DocumentAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An image or figure found in a document (§6).

    Recorded even when unreadable. `ocr_status` distinguishes 'we read it
    and there was no text' from 'we had no OCR engine' - collapsing those
    would turn a missing tool into a finding about the document."""

    __tablename__ = "document_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "organization_id"], ["documents.id", "documents.organization_id"],
            name="fk_document_assets_document_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    asset_id: Mapped[str] = mapped_column(String(300), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[DocumentAssetStatus] = mapped_column(
        _enum(DocumentAssetStatus, "document_asset_status"),
        nullable=False, default=DocumentAssetStatus.DETECTED_NOT_EXTRACTED,
        server_default=DocumentAssetStatus.DETECTED_NOT_EXTRACTED.value,
    )
    ocr_status: Mapped[DocumentOcrStatus] = mapped_column(
        _enum(DocumentOcrStatus, "document_ocr_status"),
        nullable=False, default=DocumentOcrStatus.NOT_ATTEMPTED,
        server_default=DocumentOcrStatus.NOT_ATTEMPTED.value, index=True,
    )
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Set only if a vision model interprets the image. NULL today, because
    # Level 4 is not built. An OCR string is NOT an interpretation.
    vision_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vision_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
