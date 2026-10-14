"""ClaimEvidence (Claim<->Evidence link) endpoints — tenant-scoped.

A flat top-level resource, filterable by claim_id/evidence_id, same
shape as /relationships (Phase 2's generic graph-edge table) rather
than nested under /claims or /evidence — a link genuinely belongs to
neither side more than the other.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.claim_evidence import ClaimEvidence
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.claim_evidence import ClaimEvidenceCreate, ClaimEvidenceRead, ClaimEvidenceUpdate
from app.schemas.common import Page, PaginationParams, SortParams
from app.security.dependencies import get_current_user, require_roles
from app.services import claim_evidence_service

router = APIRouter(prefix="/claim-evidence", tags=["claim-evidence"])


@router.get("", response_model=Page[ClaimEvidenceRead])
def list_claim_evidence(
    claim_id: UUID | None = Query(default=None),
    evidence_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ClaimEvidenceRead]:
    items, total = claim_evidence_service.list_claim_evidence_links(
        db,
        organization_id=current_user.organization_id,
        claim_id=claim_id,
        evidence_id=evidence_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=ClaimEvidenceRead, status_code=status.HTTP_201_CREATED)
def create_claim_evidence_link(
    payload: ClaimEvidenceCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ClaimEvidence:
    return claim_evidence_service.link_claim_evidence(
        db,
        organization_id=current_user.organization_id,
        claim_id=payload.claim_id,
        evidence_id=payload.evidence_id,
        relation=payload.relation,
        weight=payload.weight,
        notes=payload.notes,
        actor_user_id=current_user.id,
    )


@router.get("/{link_id}", response_model=ClaimEvidenceRead)
def get_claim_evidence_link(
    link_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClaimEvidence:
    return claim_evidence_service.get_link_or_404(
        db, link_id=link_id, organization_id=current_user.organization_id
    )


@router.patch("/{link_id}", response_model=ClaimEvidenceRead)
def update_claim_evidence_link(
    link_id: UUID,
    payload: ClaimEvidenceUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ClaimEvidence:
    link = claim_evidence_service.get_link_or_404(
        db, link_id=link_id, organization_id=current_user.organization_id
    )
    provided = payload.model_fields_set
    return claim_evidence_service.update_claim_evidence_link(
        db,
        link=link,
        relation=payload.relation,
        weight=payload.weight,
        weight_provided="weight" in provided,
        notes=payload.notes,
        notes_provided="notes" in provided,
        actor_user_id=current_user.id,
    )


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim_evidence_link(
    link_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    link = claim_evidence_service.get_link_or_404(
        db, link_id=link_id, organization_id=current_user.organization_id
    )
    claim_evidence_service.unlink_claim_evidence(db, link=link, actor_user_id=current_user.id)
