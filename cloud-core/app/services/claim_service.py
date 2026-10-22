"""
Claim service.

Tenant isolation for a Claim is a two-step check: the Knowledge Object
must belong to the caller's org (via get_knowledge_object_or_404), AND
the subject/object entities referenced must ALSO belong to the caller's
org (via get_entity_or_404) — otherwise a caller could link a claim on
their own Knowledge Object to another organization's Entity row.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.claim import Claim
from app.models.enums import ClaimEvidenceStrength, ClaimStatus
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.entity_service import get_entity_or_404
from app.services.knowledge_service import get_knowledge_object_or_404


class InvalidClaimObjectError(Exception):
    """Raised when an update would leave a Claim with zero or two object
    representations set — the XOR invariant enforced by
    ck_claims_object_entity_xor_value must hold after every write, not
    just at creation."""


def list_claims(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID | None,
    status: ClaimStatus | None,
    evidence_strength: ClaimEvidenceStrength | None = None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Claim], int]:
    base = select(Claim).where(Claim.organization_id == organization_id)
    if knowledge_object_id:
        base = base.where(Claim.knowledge_object_id == knowledge_object_id)
    if status:
        base = base.where(Claim.status == status)
    if evidence_strength:
        base = base.where(Claim.evidence_strength == evidence_strength)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Claim, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    )
    return list(rows), total


def get_claim_or_404(db: Session, *, claim_id: UUID, organization_id: UUID) -> Claim:
    return get_tenant_scoped_or_404(
        db, Claim, claim_id, organization_id=organization_id, not_found_message="Claim not found"
    )


def create_claim(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID,
    subject_entity_id: UUID,
    predicate: str,
    object_entity_id: UUID | None,
    object_value: str | None,
    claim_type: str | None,
    confidence: float | None,
    actor_user_id: UUID,
    section_key: str | None = None,
) -> Claim:
    get_knowledge_object_or_404(db, object_id=knowledge_object_id, organization_id=organization_id)
    get_entity_or_404(db, entity_id=subject_entity_id, organization_id=organization_id)
    if object_entity_id is not None:
        get_entity_or_404(db, entity_id=object_entity_id, organization_id=organization_id)

    claim = Claim(
        organization_id=organization_id,
        knowledge_object_id=knowledge_object_id,
        subject_entity_id=subject_entity_id,
        predicate=predicate,
        object_entity_id=object_entity_id,
        object_value=object_value,
        section_key=section_key,          # ADR-114: which knowledge section this claim belongs to
        claim_type=claim_type,
        confidence=confidence,
        status=ClaimStatus.DRAFT,
        evidence_strength=ClaimEvidenceStrength.UNVERIFIED,
        source_generated=False,
        human_reviewed=False,
    )
    db.add(claim)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="claim.created",
        resource_type="claim",
        resource_id=claim.id,
        new_value={"predicate": claim.predicate, "status": claim.status.value},
    )
    db.commit()
    db.refresh(claim)
    return claim


def update_claim(
    db: Session,
    *,
    claim: Claim,
    predicate: str | None,
    object_entity_id_provided: bool,
    object_entity_id: UUID | None,
    object_value_provided: bool,
    object_value: str | None,
    claim_type: str | None,
    confidence: float | None,
    actor_user_id: UUID,
) -> Claim:
    """`*_provided` flags distinguish "field omitted from the request"
    from "field explicitly sent as null" — see ClaimUpdate's docstring
    for the full semantics this implements. Both `_provided` flags come
    from `payload.model_dump(exclude_unset=True)` in the API layer.
    """
    old_value = {
        "predicate": claim.predicate,
        "status": claim.status.value,
        "object_entity_id": str(claim.object_entity_id) if claim.object_entity_id else None,
        "object_value": claim.object_value,
    }

    if predicate is not None:
        claim.predicate = predicate
    if claim_type is not None:
        claim.claim_type = claim_type
    if confidence is not None:
        claim.confidence = confidence

    # Resolve the object representation change, if any was requested.
    # Handled as explicit branches (rather than one merged expression)
    # because the four provided/not-provided x null/non-null
    # combinations each have a distinct, deliberate meaning — see
    # ClaimUpdate's docstring.
    if object_entity_id_provided and object_value_provided:
        if object_entity_id is not None and object_value is not None:
            raise InvalidClaimObjectError(
                "Cannot set both object_entity_id and object_value in the same request."
            )
        if object_entity_id is None and object_value is None:
            raise InvalidClaimObjectError(
                "Cannot clear both object_entity_id and object_value; exactly one must remain set."
            )
        new_entity_id, new_value = object_entity_id, object_value
    elif object_entity_id_provided:
        new_entity_id = object_entity_id
        new_value = None if object_entity_id is not None else claim.object_value
        if object_entity_id is None and claim.object_value is None:
            raise InvalidClaimObjectError(
                "Cannot clear object_entity_id: no object_value is set to fall back to. "
                "Provide object_value in the same request if you want to switch representations."
            )
    elif object_value_provided:
        new_value = object_value
        new_entity_id = None if object_value is not None else claim.object_entity_id
        if object_value is None and claim.object_entity_id is None:
            raise InvalidClaimObjectError(
                "Cannot clear object_value: no object_entity_id is set to fall back to. "
                "Provide object_entity_id in the same request if you want to switch representations."
            )
    else:
        new_entity_id, new_value = claim.object_entity_id, claim.object_value

    if (new_entity_id is not None) == (new_value is not None):
        # Defensive: every branch above should already guarantee this,
        # but the invariant is cheap to re-check and this is exactly the
        # property a future refactor of the branches above could break.
        raise InvalidClaimObjectError(
            "Update would leave the claim with zero or two object representations; "
            "exactly one of object_entity_id/object_value must remain set."
        )

    if new_entity_id is not None and new_entity_id != claim.object_entity_id:
        get_entity_or_404(db, entity_id=new_entity_id, organization_id=claim.organization_id)

    claim.object_entity_id = new_entity_id
    claim.object_value = new_value

    db.flush()
    record_audit_log(
        db,
        organization_id=claim.organization_id,
        user_id=actor_user_id,
        action="claim.updated",
        resource_type="claim",
        resource_id=claim.id,
        old_value=old_value,
        new_value={
            "predicate": claim.predicate,
            "status": claim.status.value,
            "object_entity_id": str(claim.object_entity_id) if claim.object_entity_id else None,
            "object_value": claim.object_value,
        },
    )
    db.commit()
    db.refresh(claim)
    return claim


def review_claim(
    db: Session,
    *,
    claim: Claim,
    status: ClaimStatus,
    evidence_strength: ClaimEvidenceStrength | None,
    note: str | None,
    actor_user_id: UUID,
) -> Claim:
    """The one path that transitions a Claim's review status. Always
    sets human_reviewed=True — an explicit review action is, by
    definition, a human review (see master spec section 44: uncertain
    claims must not be auto-published without review)."""
    old_value = {"status": claim.status.value, "human_reviewed": claim.human_reviewed}

    claim.status = status
    claim.human_reviewed = True
    if evidence_strength is not None:
        claim.evidence_strength = evidence_strength

    db.flush()
    record_audit_log(
        db,
        organization_id=claim.organization_id,
        user_id=actor_user_id,
        action="claim.reviewed",
        resource_type="claim",
        resource_id=claim.id,
        old_value=old_value,
        new_value={"status": claim.status.value, "note": note},
    )
    db.commit()
    db.refresh(claim)
    return claim
