"""Claim endpoints - tenant-scoped, with a dedicated /review action."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.claim import Claim
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, ClaimEvidenceStrength, ClaimStatus
from app.models.user import User
from app.schemas.claim import ClaimCreate, ClaimRead, ClaimReviewRequest, ClaimUpdate
from app.schemas.common import Page, PaginationParams, SortParams
from app.security.dependencies import get_current_user, require_roles
from app.services import claim_service

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("", response_model=Page[ClaimRead])
def list_claims(
    knowledge_object_id: UUID | None = Query(default=None),
    status_filter: ClaimStatus | None = Query(default=None, alias="status"),
    # e.g. ?evidence_strength=conflicting: claims whose VERIFIED evidence has
    # real weight on both sides (claim_evidence_service.recompute_claim_aggregate).
    # The Dashboard's "claims in conflict" count is this list's `total`.
    evidence_strength: ClaimEvidenceStrength | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ClaimRead]:
    items, total = claim_service.list_claims(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=knowledge_object_id,
        status=status_filter,
        evidence_strength=evidence_strength,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=ClaimRead, status_code=201)
def create_claim(
    payload: ClaimCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Claim:
    return claim_service.create_claim(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=payload.knowledge_object_id,
        subject_entity_id=payload.subject_entity_id,
        predicate=payload.predicate,
        object_entity_id=payload.object_entity_id,
        object_value=payload.object_value,
        claim_type=payload.claim_type,
        confidence=payload.confidence,
        actor_user_id=current_user.id,
        section_key=payload.section_key,
    )


@router.get("/{claim_id}", response_model=ClaimRead)
def get_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Claim:
    return claim_service.get_claim_or_404(db, claim_id=claim_id, organization_id=current_user.organization_id)


@router.patch("/{claim_id}", response_model=ClaimRead)
def update_claim(
    claim_id: UUID,
    payload: ClaimUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Claim:
    claim = claim_service.get_claim_or_404(db, claim_id=claim_id, organization_id=current_user.organization_id)
    # exclude_unset distinguishes "field omitted from the JSON body" from
    # "field explicitly sent as null" — see ClaimUpdate's docstring. Both
    # object_entity_id=None and object_value=None are valid DEFAULTS on
    # the schema, so the payload's attribute values alone can't tell us
    # which case we're in; only `model_fields_set` (the set of field
    # names actually present in the input, equivalent to
    # `model_dump(exclude_unset=True).keys()`) can.
    provided_fields = payload.model_fields_set
    try:
        return claim_service.update_claim(
            db,
            claim=claim,
            predicate=payload.predicate,
            object_entity_id_provided="object_entity_id" in provided_fields,
            object_entity_id=payload.object_entity_id,
            object_value_provided="object_value" in provided_fields,
            object_value=payload.object_value,
            claim_type=payload.claim_type,
            confidence=payload.confidence,
            actor_user_id=current_user.id,
        )
    except claim_service.InvalidClaimObjectError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None


@router.post("/{claim_id}/review", response_model=ClaimRead)
def review_claim(
    claim_id: UUID,
    payload: ClaimReviewRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Claim:
    claim = claim_service.get_claim_or_404(db, claim_id=claim_id, organization_id=current_user.organization_id)
    return claim_service.review_claim(
        db,
        claim=claim,
        status=payload.status,
        evidence_strength=payload.evidence_strength,
        note=payload.note,
        actor_user_id=current_user.id,
    )
