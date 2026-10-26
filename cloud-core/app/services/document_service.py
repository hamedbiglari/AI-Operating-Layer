"""
Document management service.

Every Document belongs to a Source; creating one validates the source
belongs to the SAME organization as the caller (the two-hop tenant
check pattern established for Claims in Phase 2, applied here per the
Phase 2 review's forward-looking note about tenant ownership across
Evidence/Source/Document/Graph in later phases).
"""

import hashlib
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, defer

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentExtractionStatus
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.source_service import get_source_or_404


def _hash_content(content: str | None) -> str | None:
    if not content:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def list_documents(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Document], int]:
    base = select(Document).where(Document.organization_id == organization_id)
    if source_id:
        base = base.where(Document.source_id == source_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Document, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def list_documents_with_conversion(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """A source's documents, each with its current conversion, in one query.
    At most one current conversion per document (uq_document_conversions_one_current),
    so the outer join cannot duplicate rows. `content` is not loaded."""
    where = (Document.organization_id == organization_id, Document.source_id == source_id)
    total = db.execute(select(func.count()).select_from(Document).where(*where)).scalar_one()
    stmt = (
        select(Document, DocumentConversion.id, DocumentConversion.conversion_status, DocumentConversion.needs_review)
        .outerjoin(DocumentConversion, and_(DocumentConversion.document_id == Document.id,
                                            DocumentConversion.is_current))
        .where(*where)
        .options(defer(Document.content))
    )
    rows = db.execute(apply_sort(stmt, Document, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).all()
    return [
        {"document": doc,
         "current_conversion": {"id": cid, "status": status, "needs_review": review} if cid else None}
        for doc, cid, status, review in rows
    ], total


def get_document_or_404(db: Session, *, document_id: UUID, organization_id: UUID) -> Document:
    return get_tenant_scoped_or_404(
        db, Document, document_id, organization_id=organization_id, not_found_message="Document not found"
    )


def create_document(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID,
    title: str,
    content: str | None,
    language: str,
    mime_type: str,
    storage_path: str | None,
    actor_user_id: UUID,
) -> Document:
    # Tenant check on the parent Source — a document can never be
    # attached to another organization's source, even by a caller who
    # is otherwise fully authenticated and authorized.
    get_source_or_404(db, source_id=source_id, organization_id=organization_id)

    document = Document(
        organization_id=organization_id,
        source_id=source_id,
        title=title,
        content=content,
        language=language,
        content_hash=_hash_content(content),
        mime_type=mime_type,
        storage_path=storage_path,
        file_size=len(content.encode("utf-8")) if content else None,
        extraction_status=DocumentExtractionStatus.PENDING,
    )
    db.add(document)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="document.created",
        resource_type="document",
        resource_id=document.id,
        new_value={"title": document.title, "source_id": str(source_id)},
    )
    db.commit()
    db.refresh(document)
    return document


def update_document(
    db: Session,
    *,
    document: Document,
    title: str | None,
    content: str | None,
    language: str | None,
    extraction_status: DocumentExtractionStatus | None,
    actor_user_id: UUID,
) -> Document:
    old_value = {"title": document.title, "version": document.version}

    if title is not None:
        document.title = title
    if content is not None:
        document.content = content
        document.content_hash = _hash_content(content)
        document.file_size = len(content.encode("utf-8"))
        document.version += 1
        # Content changed underneath any existing chunks — they no
        # longer reflect this document's text at all (not just "stale
        # embeddings"; the text itself is wrong), so delete them rather
        # than leaving them to silently poison chunk listing / search
        # results. /documents/{id}/process regenerates them from the
        # new content on request.
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        document.extraction_status = DocumentExtractionStatus.PENDING
    if language is not None:
        document.language = language
    if extraction_status is not None:
        document.extraction_status = extraction_status

    db.flush()
    record_audit_log(
        db,
        organization_id=document.organization_id,
        user_id=actor_user_id,
        action="document.updated",
        resource_type="document",
        resource_id=document.id,
        old_value=old_value,
        new_value={"title": document.title, "version": document.version},
    )
    db.commit()
    db.refresh(document)
    return document
