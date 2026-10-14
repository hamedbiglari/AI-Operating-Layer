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
) -> tuple[list[Source], int]:
    base = select(Source).where(Source.organization_id == organization_id)
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
