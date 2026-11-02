"""Source management service — every query is scoped to organization_id."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.source import Source
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log


def list_sources(
    db: Session,
    *,
    organization_id: UUID,
    source_type: str | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
    include_archived: bool = False,
) -> tuple[list[Source], int]:
    base = select(Source).where(Source.organization_id == organization_id)
    if not include_archived:
        base = base.where(Source.archived_at.is_(None))
    if source_type:
        base = base.where(Source.source_type == source_type)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Source, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_source_or_404(db: Session, *, source_id: UUID, organization_id: UUID) -> Source:
    return get_tenant_scoped_or_404(
        db, Source, source_id, organization_id=organization_id, not_found_message="Source not found"
    )


def create_source(
    db: Session,
    *,
    organization_id: UUID,
    source_type: str,
    title: str,
    author: str | None,
    url: str | None,
    doi: str | None,
    pmid: str | None,
    isbn: str | None,
    publisher: str | None,
    publication_date,
    access_status,
    rights_status,
    reliability_score: float | None,
    metadata: dict,
    actor_user_id: UUID,
) -> Source:
    source = Source(
        organization_id=organization_id,
        source_type=source_type,
        title=title,
        author=author,
        url=url,
        doi=doi,
        pmid=pmid,
        isbn=isbn,
        publisher=publisher,
        publication_date=publication_date,
        access_status=access_status,
        rights_status=rights_status,
        reliability_score=reliability_score,
        metadata_=metadata,
    )
    db.add(source)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="source.created",
        resource_type="source",
        resource_id=source.id,
        new_value={"source_type": source.source_type, "title": source.title},
    )
    db.commit()
    db.refresh(source)
    return source


def update_source(
    db: Session,
    *,
    source: Source,
    actor_user_id: UUID,
    **fields,
) -> Source:
    old_value = {"title": source.title, "access_status": source.access_status.value}

    for field_name, value in fields.items():
        if value is None:
            continue
        if field_name == "metadata":
            source.metadata_ = value
        else:
            setattr(source, field_name, value)

    db.flush()
    record_audit_log(
        db,
        organization_id=source.organization_id,
        user_id=actor_user_id,
        action="source.updated",
        resource_type="source",
        resource_id=source.id,
        old_value=old_value,
        new_value={"title": source.title, "access_status": source.access_status.value},
    )
    db.commit()
    db.refresh(source)
    return source


def set_archived(db: Session, *, source: Source, actor_user_id: UUID, archived: bool, reason: str | None = None) -> Source:
    """Archive or unarchive a source (V5-source-detail-archive). Archiving keeps everything (documents, evidence,
    claims); the source only leaves the lists until it is unarchived. Archiving an archived source keeps its date."""
    from datetime import datetime, timezone

    old = {"archived_at": source.archived_at.isoformat() if source.archived_at else None, "archive_reason": source.archive_reason}
    if archived:
        source.archived_at = source.archived_at or datetime.now(timezone.utc)
        source.archive_reason = (reason or "").strip() or None
    else:
        source.archived_at = None
        source.archive_reason = None
    record_audit_log(
        db,
        organization_id=source.organization_id,
        user_id=actor_user_id,
        action="source.archived" if archived else "source.unarchived",
        resource_type="source",
        resource_id=source.id,
        old_value=old,
        new_value={"archived_at": source.archived_at.isoformat() if source.archived_at else None,
                   "archive_reason": source.archive_reason},
    )
    db.commit()
    db.refresh(source)
    return source


def delete_source(db: Session, *, source: Source, actor_user_id: UUID) -> None:
    """Delete a source and its documents (V5-source-detail-delete). Refused (409) while anything else depends on it:
    its evidence (and so the claim links built on it), publication citations and research dependencies would all
    cascade away with it, silently changing claims and published text. Those are removed first, on purpose."""
    from fastapi import HTTPException, status as http_status
    from sqlalchemy import delete, or_

    from app.models.document import Document
    from app.models.evidence import Evidence
    from app.models.publication import PublicationReference, SentenceSource
    from app.models.research_dependency import SourceDependency

    def count(model, *where) -> int:
        return db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()

    org = source.organization_id
    evidence = count(Evidence, Evidence.organization_id == org, Evidence.source_id == source.id)
    citations = (count(SentenceSource, SentenceSource.source_id == source.id)
                 + count(PublicationReference, PublicationReference.source_id == source.id))
    dependencies = count(SourceDependency, or_(SourceDependency.source_id == source.id,
                                               SourceDependency.depends_on_source_id == source.id))
    if evidence or citations or dependencies:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(f"Cannot delete source: {evidence} evidence records, {citations} publication citations and "
                    f"{dependencies} research dependencies use it. Remove them first."),
        )
    documents = count(Document, Document.organization_id == org, Document.source_id == source.id)
    record_audit_log(
        db,
        organization_id=org,
        user_id=actor_user_id,
        action="source.deleted",
        resource_type="source",
        resource_id=source.id,
        old_value={"source_type": source.source_type, "title": source.title, "documents": documents},
    )
    source_id = source.id
    db.expunge(source)
    # A SQL delete, so the database's own ON DELETE CASCADE removes the documents (and their conversions, chunks
    # and artifacts) rather than the ORM trying to null their required source_id.
    db.execute(delete(Source).where(Source.id == source_id, Source.organization_id == org))
    db.commit()
