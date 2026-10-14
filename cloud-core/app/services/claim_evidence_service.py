"""
ClaimEvidence link service — the "Conflict foundations" piece of Phase
4.

Tenant isolation is the same two-step discipline established for Claim
(entities) and Document (source) in earlier phases: `claim_id` must
belong to the caller's org (via claim_service.get_claim_or_404) AND
`evidence_id` must ALSO belong to the caller's org (via
evidence_service.get_evidence_or_404) before a link between them can be
created.

recompute_claim_aggregate() is the mechanism this phase adds for
detecting disagreement between a Claim's linked Evidence: it is called
after every link create/update/delete and after every Evidence review
transition (since VERIFIED-ness gates whether a link counts). It is
DELIBERATELY a documented heuristic, not a final scientific-consensus
algorithm — replacing it with something more sophisticated (e.g.
meta-analytic pooling) is explicitly future work for the Research/Query
engine phases (5-6). What this phase guarantees is narrower and load-
bearing on its own: a Claim's `evidence_strength` is never a stale,
manually-set value once real Evidence is linked to it, and an APPROVED
Claim is never left presented as settled once verified evidence on both
sides of it exists (master spec section 44's "do not automatically
publish uncertain claims" cuts both ways: it also means don't leave a
claim looking un-uncertain once it demonstrably is).
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort
from fastapi import HTTPException, status

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.enums import ClaimEvidenceStrength, ClaimStatus, EvidenceRelation, EvidenceStatus, EvidenceStrength
from app.models.evidence import Evidence
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.claim_service import get_claim_or_404
from app.services.evidence_service import get_evidence_or_404

# GRADE-style strength -> numeric weight used when a link doesn't
# override it with an explicit `weight` (see ClaimEvidence.weight's
# docstring). Deliberately simple/monotonic and documented here as the
# single source of truth for the mapping.
_STRENGTH_WEIGHT = {
    EvidenceStrength.VERY_LOW: 0.25,
    EvidenceStrength.LOW: 0.5,
    EvidenceStrength.MODERATE: 0.75,
    EvidenceStrength.HIGH: 1.0,
}

# A conflict is only flagged when BOTH sides carry non-trivial weight —
# one HIGH-strength contradiction against a single VERY_LOW-strength
# support (0.25) should not immediately read as "conflicting"; that's
# just "weakly supported, one strong objection", i.e. INSUFFICIENT/WEAK.
_CONFLICT_MIN_WEIGHT_PER_SIDE = 0.5


def _effective_weight(link: ClaimEvidence, evidence: Evidence) -> float:
    if link.weight is not None:
        return float(link.weight)
    return _STRENGTH_WEIGHT[evidence.evidence_strength]


def list_claim_evidence_links(
    db: Session,
    *,
    organization_id: UUID,
    claim_id: UUID | None,
    evidence_id: UUID | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ClaimEvidence], int]:
    base = select(ClaimEvidence).where(ClaimEvidence.organization_id == organization_id)
    if claim_id:
        base = base.where(ClaimEvidence.claim_id == claim_id)
    if evidence_id:
        base = base.where(ClaimEvidence.evidence_id == evidence_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ClaimEvidence, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_link_or_404(db: Session, *, link_id: UUID, organization_id: UUID) -> ClaimEvidence:
    return get_tenant_scoped_or_404(
        db, ClaimEvidence, link_id, organization_id=organization_id, not_found_message="Claim/Evidence link not found"
    )


def link_claim_evidence(
    db: Session,
    *,
    organization_id: UUID,
    claim_id: UUID,
    evidence_id: UUID,
    relation: EvidenceRelation,
    weight: float | None,
    notes: str | None,
    actor_user_id: UUID,
) -> ClaimEvidence:
    get_claim_or_404(db, claim_id=claim_id, organization_id=organization_id)
    get_evidence_or_404(db, evidence_id=evidence_id, organization_id=organization_id)

    link = ClaimEvidence(
        organization_id=organization_id,
        claim_id=claim_id,
        evidence_id=evidence_id,
        relation=relation,
        weight=weight,
        notes=notes,
    )
    db.add(link)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Claim is already linked to this Evidence — update the existing link instead.",
        ) from None

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="claim_evidence.linked",
        resource_type="claim_evidence",
        resource_id=link.id,
        new_value={"claim_id": str(claim_id), "evidence_id": str(evidence_id), "relation": relation.value},
    )
    db.commit()
    db.refresh(link)

    recompute_claim_aggregate(db, claim_id=claim_id, actor_user_id=actor_user_id)
    db.refresh(link)
    return link


def update_claim_evidence_link(
    db: Session,
    *,
    link: ClaimEvidence,
    relation: EvidenceRelation | None,
    weight: float | None,
    weight_provided: bool,
    notes: str | None,
    notes_provided: bool,
    actor_user_id: UUID,
) -> ClaimEvidence:
    old_value = {"relation": link.relation.value, "weight": float(link.weight) if link.weight is not None else None}

    if relation is not None:
        link.relation = relation
    if weight_provided:
        link.weight = weight
    if notes_provided:
        link.notes = notes

    db.flush()
    record_audit_log(
        db,
        organization_id=link.organization_id,
        user_id=actor_user_id,
        action="claim_evidence.updated",
        resource_type="claim_evidence",
        resource_id=link.id,
        old_value=old_value,
        new_value={"relation": link.relation.value, "weight": float(link.weight) if link.weight is not None else None},
    )
    db.commit()
    db.refresh(link)

    recompute_claim_aggregate(db, claim_id=link.claim_id, actor_user_id=actor_user_id)
    db.refresh(link)
    return link


def unlink_claim_evidence(db: Session, *, link: ClaimEvidence, actor_user_id: UUID) -> None:
    claim_id = link.claim_id
    organization_id = link.organization_id

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="claim_evidence.unlinked",
        resource_type="claim_evidence",
        resource_id=link.id,
        old_value={"claim_id": str(claim_id), "evidence_id": str(link.evidence_id), "relation": link.relation.value},
    )
    db.delete(link)
    db.commit()

    recompute_claim_aggregate(db, claim_id=claim_id, actor_user_id=actor_user_id)


def recompute_claim_aggregate(db: Session, *, claim_id: UUID, actor_user_id: UUID | None) -> Claim:
    """Roll up every VERIFIED Evidence row linked to `claim_id` into the
    Claim's `evidence_strength` (see module docstring for the full
    rationale). Only VERIFIED evidence counts — DRAFT/PENDING_REVIEW/
    REJECTED evidence must not move a Claim's aggregate, mirroring the
    same "no auto-publish on unreviewed content" principle Claim.status
    already follows (section 44).

    Safety guardrail: if the recompute detects genuine conflict (real
    weight on both SUPPORTS and CONTRADICTS) and the Claim is currently
    APPROVED, it is automatically downgraded to DISPUTED — approval is
    a human action (review_claim), but a claim silently ceasing to
    deserve that approval is exactly the failure mode "Conflict
    foundations" exists to catch. The claim is never auto-upgraded to
    APPROVED; that direction always requires a human review action.
    """
    claim = db.get(Claim, claim_id)
    if claim is None:  # pragma: no cover - defensive; FK guarantees existence
        raise ValueError(f"Claim {claim_id} not found during aggregate recompute")

    rows = db.execute(
        select(ClaimEvidence, Evidence)
        .join(Evidence, ClaimEvidence.evidence_id == Evidence.id)
        .where(ClaimEvidence.claim_id == claim_id, Evidence.status == EvidenceStatus.VERIFIED)
    ).all()

    support_weight = 0.0
    contradict_weight = 0.0
    for link, evidence in rows:
        w = _effective_weight(link, evidence)
        if link.relation == EvidenceRelation.SUPPORTS:
            support_weight += w
        elif link.relation == EvidenceRelation.CONTRADICTS:
            contradict_weight += w
        elif link.relation == EvidenceRelation.MIXED:
            support_weight += w / 2
            contradict_weight += w / 2
        # NEUTRAL contributes to neither side.

    is_conflicting = (
        support_weight >= _CONFLICT_MIN_WEIGHT_PER_SIDE and contradict_weight >= _CONFLICT_MIN_WEIGHT_PER_SIDE
    )

    if not rows:
        new_strength = ClaimEvidenceStrength.UNVERIFIED
    elif is_conflicting:
        new_strength = ClaimEvidenceStrength.CONFLICTING
    else:
        net = support_weight - contradict_weight
        if net <= 0:
            new_strength = ClaimEvidenceStrength.INSUFFICIENT
        elif net < 1.0:
            new_strength = ClaimEvidenceStrength.WEAK
        elif net < 2.0:
            new_strength = ClaimEvidenceStrength.MODERATE
        else:
            new_strength = ClaimEvidenceStrength.STRONG

    old_strength = claim.evidence_strength
    old_status = claim.status
    strength_changed = new_strength != old_strength
    claim.evidence_strength = new_strength

    status_auto_downgraded = False
    if is_conflicting and claim.status == ClaimStatus.APPROVED:
        claim.status = ClaimStatus.DISPUTED
        status_auto_downgraded = True

    if strength_changed or status_auto_downgraded:
        db.flush()
        record_audit_log(
            db,
            organization_id=claim.organization_id,
            user_id=actor_user_id,
            action="claim.evidence_aggregate_recomputed",
            resource_type="claim",
            resource_id=claim.id,
            old_value={"evidence_strength": old_strength.value, "status": old_status.value},
            new_value={
                "evidence_strength": new_strength.value,
                "status": claim.status.value,
                "support_weight": round(support_weight, 3),
                "contradict_weight": round(contradict_weight, 3),
                "auto_downgraded": status_auto_downgraded,
            },
        )
        db.commit()
        db.refresh(claim)

    return claim
