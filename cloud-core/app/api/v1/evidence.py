"""Evidence endpoints — tenant-scoped, with a dedicated /review action
(same split as /claims/{id}/review — a plain field edit must never
silently flip review status)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, EvidenceStatus
from app.models.evidence import Evidence
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.evidence import EvidenceCreate, EvidenceRead, EvidenceReviewRequest, EvidenceUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import evidence_service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("", response_model=Page[EvidenceRead])
def list_evidence(
    source_id: UUID | None = Query(default=None),
    document_id: UUID | None = Query(default=None),
    study_type: str | None = Query(default=None),
    status_filter: EvidenceStatus | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[EvidenceRead]:
    items, total = evidence_service.list_evidence(
        db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        document_id=document_id,
        study_type=study_type,
        status_filter=status_filter,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=EvidenceRead, status_code=201)
def create_evidence(
    payload: EvidenceCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Evidence:
    return evidence_service.create_evidence(
        db,
        organization_id=current_user.organization_id,
        source_id=payload.source_id,
        document_id=payload.document_id,
        document_chunk_id=payload.document_chunk_id,
        study_type=payload.study_type,
        directness=payload.directness,
        evidence_strength=payload.evidence_strength,
        summary=payload.summary,
        sample_size=payload.sample_size,
        population=payload.population,
        actor_user_id=current_user.id,
    )


@router.get("/{evidence_id}", response_model=EvidenceRead)
def get_evidence(
    evidence_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Evidence:
    return evidence_service.get_evidence_or_404(
        db, evidence_id=evidence_id, organization_id=current_user.organization_id
    )


@router.patch("/{evidence_id}", response_model=EvidenceRead)
def update_evidence(
    evidence_id: UUID,
    payload: EvidenceUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Evidence:
    evidence = evidence_service.get_evidence_or_404(
        db, evidence_id=evidence_id, organization_id=current_user.organization_id
    )
    return evidence_service.update_evidence(
        db,
        evidence=evidence,
        actor_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )


@router.post("/{evidence_id}/review", response_model=EvidenceRead)
def review_evidence(
    evidence_id: UUID,
    payload: EvidenceReviewRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Evidence:
    evidence = evidence_service.get_evidence_or_404(
        db, evidence_id=evidence_id, organization_id=current_user.organization_id
    )
    return evidence_service.review_evidence(
        db,
        evidence=evidence,
        status=payload.status,
        evidence_strength=payload.evidence_strength,
        note=payload.note,
        actor_user_id=current_user.id,
    )
