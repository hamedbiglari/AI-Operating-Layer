"""
DocumentChunk: a semantically-chunked piece of a Document, with its
vector embedding (master spec section 15).

organization_id is a deliberate addition beyond section 15's literal
field list — same rationale applied consistently since Phase 2's
KnowledgeVersion: section 8 makes organization_id mandatory on every
tenant-owned table without exception, and denormalizing it here means
every tenant-scoped chunk query (including the pgvector similarity
search in document_chunk_service.py) filters directly on this column
instead of joining through Document -> Source first.

The embedding dimension is read from settings.EMBEDDING_DIMENSIONS at
import time (see app/core/config.py) — configurable via environment
variable, but fixed for a given database once migrated, exactly as the
Phase 0 design note requires ("Do not hard-code assumptions that
prevent changing embedding models later" means "make it an environment
setting", not "make every row independently variable-length": pgvector
itself requires a fixed dimension per column). Changing
EMBEDDING_DIMENSIONS after data exists requires a new migration that
alters the column (and almost certainly re-embedding existing rows).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_chunk_index"),
    )

    # No TimestampMixin here: section 15's literal field list has only
    # `created_at` (chunks are immutable — re-chunking a document
    # deletes and recreates its chunks rather than editing them in
    # place), so `updated_at` would be a pure no-op column. Every other
    # table in this codebase uses TimestampMixin for consistency; this
    # is the one deliberate, documented exception.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=utcnow, nullable=False
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DocumentChunk document_id={self.document_id} index={self.chunk_index}>"
