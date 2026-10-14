"""
Document chunking, embedding, and pgvector similarity search — the
technical centerpiece of Phase 3.

Processing is synchronous (called directly from the API request) rather
than a Celery task for now: Redis/Celery worker infrastructure was only
scaffolded (empty `app/workers/`) in Phase 0, and wiring up an actual
worker process/queue is a bigger, separate piece of infrastructure work
than "chunk this document" needs to justify on its own. Master spec
section 43 lists `chunk_document`/`generate_embeddings` as worker job
types for when ingestion volume needs it (the "1000 articles" scale
scenario in section 45) — moving this function's body into a Celery
task later is a small, mechanical change since the function signature
here doesn't assume anything about being called synchronously.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.integrations.embeddings.base import EmbeddingProvider
from app.integrations.embeddings.deterministic import get_embedding_provider
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentExtractionStatus
from app.schemas.document_chunk import DocumentChunkSearchResult, DocumentChunkSummary
from app.security.tenant import get_tenant_scoped_or_404
from app.services.chunking import chunk_text
from app.services.document_service import get_document_or_404


def to_summary(chunk: DocumentChunk) -> DocumentChunkSummary:
    return DocumentChunkSummary(
        id=chunk.id,
        organization_id=chunk.organization_id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        token_count=chunk.token_count,
        has_embedding=chunk.embedding is not None,
        metadata_value=chunk.metadata_,
    )


def list_chunks(
    db: Session, *, document_id: UUID, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[DocumentChunkSummary], int]:
    get_document_or_404(db, document_id=document_id, organization_id=organization_id)

    base = select(DocumentChunk).where(
        DocumentChunk.document_id == document_id,
        DocumentChunk.organization_id == organization_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, DocumentChunk, sort, "chunk_index", SortDirection.ASC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [to_summary(r) for r in rows], total


def get_chunk_or_404(db: Session, *, chunk_id: UUID, organization_id: UUID) -> DocumentChunk:
    return get_tenant_scoped_or_404(
        db,
        DocumentChunk,
        chunk_id,
        organization_id=organization_id,
        not_found_message="Document chunk not found",
    )


def process_document(
    db: Session,
    *,
    document_id: UUID,
    organization_id: UUID,
    embedding_provider: EmbeddingProvider | None = None,
) -> tuple[Document, list[DocumentChunkSummary]]:
    """Chunk `document.content`, embed each chunk, and store them —
    replacing any chunks that already existed for this document (so
    calling this twice is safe and idempotent, not additive)."""
    document = get_document_or_404(db, document_id=document_id, organization_id=organization_id)
    provider = embedding_provider or get_embedding_provider()

    document.extraction_status = DocumentExtractionStatus.EXTRACTING
    db.flush()

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

    pieces = chunk_text(document.content or "")
    if not pieces:
        document.extraction_status = DocumentExtractionStatus.FAILED
        db.commit()
        db.refresh(document)
        return document, []

    embeddings = provider.embed_batch(pieces)
    chunks: list[DocumentChunk] = []
    for index, (piece, vector) in enumerate(zip(pieces, embeddings, strict=True)):
        chunk = DocumentChunk(
            organization_id=organization_id,
            document_id=document.id,
            chunk_index=index,
            content=piece,
            token_count=len(piece.split()),
            embedding=vector,
        )
        db.add(chunk)
        chunks.append(chunk)

    document.extraction_status = DocumentExtractionStatus.EXTRACTED
    db.commit()
    db.refresh(document)
    for chunk in chunks:
        db.refresh(chunk)

    return document, [to_summary(c) for c in chunks]


def search_similar_chunks(
    db: Session,
    *,
    organization_id: UUID,
    query_text: str,
    limit: int,
    document_id: UUID | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[DocumentChunkSearchResult]:
    """Nearest-neighbor search over this organization's chunks using
    pgvector's cosine distance operator. Tenant-scoped by
    organization_id in the WHERE clause — never just "search everything
    and hope the caller only sees their own," since pgvector has no
    concept of tenancy on its own.

    Reminder: with the placeholder DeterministicHashEmbeddingProvider
    (see that module's docstring), "nearest" has no semantic meaning —
    this proves the query mechanism works, not that results are useful
    for a real search feature yet.
    """
    provider = embedding_provider or get_embedding_provider()
    query_vector = provider.embed(query_text)

    stmt = select(
        DocumentChunk,
        DocumentChunk.embedding.cosine_distance(query_vector).label("distance"),
    ).where(
        DocumentChunk.organization_id == organization_id,
        DocumentChunk.embedding.is_not(None),
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)

    stmt = stmt.order_by("distance").limit(limit)
    rows = db.execute(stmt).all()

    return [
        DocumentChunkSearchResult(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            distance=float(distance),
        )
        for chunk, distance in rows
    ]
