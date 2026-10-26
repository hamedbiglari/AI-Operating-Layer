"""
Source endpoints — tenant-scoped, writes require KNOWLEDGE_EDITOR_ROLES.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.source import Source
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.document import DocumentWithConversion
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
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
