"""
Source endpoints — tenant-scoped, writes require KNOWLEDGE_EDITOR_ROLES.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, UserRole
from app.models.source import Source
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.document import DocumentWithConversion
from app.schemas.source import SourceArchive, SourceCreate, SourceRead, SourceUpdate
from app.schemas.source_overview import (
    SourceDerivedStatus,
    SourceOverviewItem,
    SourceOverviewPage,
    SourceOverviewSort,
)
from app.security.dependencies import get_current_user, require_roles
from app.services import document_service, source_overview_service, source_service

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=Page[SourceRead])
def list_sources(
    source_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SourceRead]:
    items, total = source_service.list_sources(
        db,
        organization_id=current_user.organization_id,
        source_type=source_type,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# Registered before /{source_id}, which would otherwise match "overview".
@router.get("/overview", response_model=SourceOverviewPage)
def sources_overview(
    source_id: UUID | None = Query(default=None, alias="id"),
    search: str | None = Query(default=None, max_length=500),
    source_type: str | None = Query(default=None, max_length=100),
    status_filter: SourceDerivedStatus | None = Query(default=None, alias="status"),
    sort: SourceOverviewSort = Query(default=SourceOverviewSort.UPDATED),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Archived sources are hidden unless asked for (V5-source-archive-state); ?id= returns one either way.
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceOverviewPage:
    """The Sources list's rows: each source with its derived status, counts
    and last activity, filtered, ordered and paged server-side. With ?id= it
    is the Source detail header's one row, whatever filters the list had, and
    an unknown id is a 404."""
    if source_id:
        source_service.get_source_or_404(db, source_id=source_id, organization_id=current_user.organization_id)
        search = source_type = status_filter = None
        offset = 0
    rows, total, counts_by_status = source_overview_service.get_overview(
        db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
        source_id=source_id,
        search=search,
        source_type=source_type,
        status=status_filter,
        sort=sort,
        include_archived=include_archived,
    )
    items = [
        SourceOverviewItem(
            **SourceRead.model_validate(r["source"]).model_dump(),
            counts=r["counts"],
            derived_status=r["derived_status"],
            last_activity_at=r["last_activity_at"],
            file_size=r["file_size"],
            mime_type=r["mime_type"],
        )
        for r in rows
    ]
    return SourceOverviewPage(
        items=items, total=total, limit=limit, offset=offset, counts_by_status=counts_by_status
    )


# The export holds every matching row; past this the list should be filtered first (V5-source-export).
EXPORT_MAX_ROWS = 10000
EXPORT_COLUMNS = ["id", "title", "source_type", "status", "documents", "knowledge_objects", "claims", "evidence",
                  "author", "publisher", "publication_date", "url", "doi", "last_activity_at"]


def _csv_cell(value) -> str:
    """A spreadsheet must not run a title as a formula (CSV injection): a cell starting with = + - @ or a control
    character is prefixed with an apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/export.csv")
def export_sources(
    search: str | None = Query(default=None, max_length=500),
    source_type: str | None = Query(default=None, max_length=100),
    status_filter: SourceDerivedStatus | None = Query(default=None, alias="status"),
    sort: SourceOverviewSort = Query(default=SourceOverviewSort.UPDATED),
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """The Sources list as CSV (V5-source-export): the same filters and order as /sources/overview, every matching
    row in one response (up to EXPORT_MAX_ROWS), UTF-8 with a BOM so spreadsheet programs read Persian titles."""
    import csv
    import io

    rows, total, _ = source_overview_service.get_overview(
        db, organization_id=current_user.organization_id, limit=EXPORT_MAX_ROWS, offset=0,
        search=search, source_type=source_type, status=status_filter, sort=sort, include_archived=include_archived,
    )
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(EXPORT_COLUMNS)
    for r in rows:
        s, c = r["source"], r["counts"]
        writer.writerow([_csv_cell(v) for v in (
            s.id, s.title, s.source_type, SourceDerivedStatus(r["derived_status"]).value, c["documents"], c["knowledge_objects"], c["claims"],
            c["evidence"], s.author, s.publisher, s.publication_date, s.url, s.doi, r["last_activity_at"].isoformat())])
    headers = {"Content-Disposition": 'attachment; filename="sources.csv"', "X-Total-Count": str(total)}
    return Response(content="\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("", response_model=SourceRead, status_code=201)
def create_source(
    payload: SourceCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Source:
    return source_service.create_source(
        db,
        organization_id=current_user.organization_id,
        source_type=payload.source_type,
        title=payload.title,
        author=payload.author,
        url=payload.url,
        doi=payload.doi,
        pmid=payload.pmid,
        isbn=payload.isbn,
        publisher=payload.publisher,
        publication_date=payload.publication_date,
        access_status=payload.access_status,
        rights_status=payload.rights_status,
        reliability_score=payload.reliability_score,
        metadata=payload.metadata,
        actor_user_id=current_user.id,
    )


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Source:
    return source_service.get_source_or_404(
        db, source_id=source_id, organization_id=current_user.organization_id
    )


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Source:
    source = source_service.get_source_or_404(
        db, source_id=source_id, organization_id=current_user.organization_id
    )
    return source_service.update_source(
        db,
        source=source,
        actor_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )


@router.post("/{source_id}/archive", response_model=SourceRead)
def archive_source(
    source_id: UUID,
    payload: SourceArchive | None = None,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> Source:
    """Archive a source (owner or admin): it leaves the lists; nothing is deleted. Audit-logged."""
    source = source_service.get_source_or_404(db, source_id=source_id, organization_id=current_user.organization_id)
    return source_service.set_archived(db, source=source, actor_user_id=current_user.id, archived=True,
                                       reason=payload.reason if payload else None)


@router.post("/{source_id}/unarchive", response_model=SourceRead)
def unarchive_source(
    source_id: UUID,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> Source:
    """Bring an archived source back into the lists (owner or admin). Audit-logged."""
    source = source_service.get_source_or_404(db, source_id=source_id, organization_id=current_user.organization_id)
    return source_service.set_archived(db, source=source, actor_user_id=current_user.id, archived=False)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: UUID,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a source and its documents; owner or admin only. 409 while evidence, publication citations or research
    dependencies use it (V5-source-detail-delete)."""
    source = source_service.get_source_or_404(db, source_id=source_id, organization_id=current_user.organization_id)
    source_service.delete_source(db, source=source, actor_user_id=current_user.id)
    return Response(status_code=204)


@router.get("/{source_id}/documents", response_model=Page[DocumentWithConversion])
def list_documents_for_source(
    source_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[DocumentWithConversion]:
    """The Source detail's documents, each with its current conversion, so the
    list needs no call per document."""
    source_service.get_source_or_404(
        db, source_id=source_id, organization_id=current_user.organization_id
    )
    rows, total = document_service.list_documents_with_conversion(
        db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    items = [
        DocumentWithConversion(
            **DocumentWithConversion.model_validate(r["document"]).model_dump(exclude={"current_conversion"}),
            current_conversion=r["current_conversion"],
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)
