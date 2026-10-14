"""
Document: a specific piece of content extracted from a Source (master
spec section 14). One Source (e.g. a journal, a website) can have
several Documents (e.g. different articles/pages from it) — that's why
this is a separate table rather than a `content` column on Source.
"""

import uuid

from sqlalchemy import BigInteger, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentExtractionStatus


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Phase 3 stores extracted text inline. Very large documents / binary
    # originals belong in object storage behind `storage_path` — that
    # integration is future work (Phase 9+ adapters own real file I/O);
    # `content` here is always the plain-text extraction, never binary.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en", server_default="en")

    # SHA-256 of `content`, maintained by the service layer on every
    # write — the groundwork for the duplicate-detection step in the
    # ingestion pipeline (section 44); actual cross-document dedup
    # logic is future work once real ingestion volume exists (section 45).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/plain", server_default="text/plain")
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    extraction_status: Mapped[DocumentExtractionStatus] = mapped_column(
        SAEnum(
            DocumentExtractionStatus,
            name="document_extraction_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DocumentExtractionStatus.PENDING,
        server_default=DocumentExtractionStatus.PENDING.value,
    )

    source: Mapped["Source"] = relationship(back_populates="documents")  # noqa: F821
    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Document id={self.id} title={self.title!r} status={self.extraction_status.value}>"
