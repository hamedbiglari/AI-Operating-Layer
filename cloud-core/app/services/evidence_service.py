"""
Evidence service.

Tenant isolation for an Evidence row follows the same two/three-step
discipline established for Claim (subject/object entities) and Document
(source_id) in earlier phases: `source_id` must belong to the caller's
org, and if `document_id` and/or `document_chunk_id` are given, they
must ALSO belong to the caller's org — AND `document_chunk_id`, if
given, must belong to `document_id` (not just to a sibling document in
the same org), AND `document_id` must belong to `source_id` (not just
to a sibling source in the same org). Skipping any one of these checks
would let a caller attach an Evidence row to another org's Document, or
mismatch a chunk to the wrong document, entirely undetected.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import EvidenceStatus
from app.models.evidence import Evidence
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.document_chunk_service import get_chunk_or_404
from app.services.document_service import get_document_or_404
from app.services.source_service import get_source_or_404


def _validate_provenance_chain(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID,
    document_id: UUID | None,
    document_chunk_id: UUID | None,
) -> None:
    get_source_or_404(db, source_id=source_id, organization_id=organization_id)

    if document_id is not None:
        document = get_document_or_404(db, document_id=document_id, organization_id=organization_id)
        if document.source_id != source_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="document_id does not belong to the given source_id",
            )

    if document_chunk_id is not None:
        if document_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="document_chunk_id requires document_id to also be provided",
            )
        chunk = get_chunk_or_404(db, chunk_id=document_chunk_id, organization_id=organization_id)
        if chunk.document_id != document_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="document_chunk_id does not belong to the given document_id",
            )


def list_evidence(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID | None,
    document_id: UUID | None,
    study_type: str | None,
    status_filter: EvidenceStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Evidence], int]:
    base = select(Evidence).where(Evidence.organization_id == organization_id)
    if source_id:
        base = base.where(Evidence.source_id == source_id)
    if document_id:
        base = base.where(Evidence.document_id == document_id)
    if study_type:
        base = base.where(Evidence.study_type == study_type)
    if status_filter:
        base = base.where(Evidence.status == status_filter)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Evidence, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_evidence_or_404(db: Session, *, evidence_id: UUID, organization_id: UUID) -> Evidence:
    return get_tenant_scoped_or_404(
        db, Evidence, evidence_id, organization_id=organization_id, not_found_message="Evidence not found"
    )


def create_evidence(
    db: Session,
    *,
    organization_id: UUID,
    source_id: UUID,
    document_id: UUID | None,
    document_chunk_id: UUID | None,
    study_type: str | None,
    directness,
    evidence_strength,
    summary: str,
    sample_size: int | None,
    population: str | None,
    actor_user_id: UUID,
) -> Evidence:
    _validate_provenance_chain(
        db,
        organization_id=organization_id,
        source_id=source_id,
        document_id=document_id,
        document_chunk_id=document_chunk_id,
    )

    evidence = Evidence(
        organization_id=organization_id,
        source_id=source_id,
        document_id=document_id,
        document_chunk_id=document_chunk_id,
        study_type=study_type,
        directness=directness,
        evidence_strength=evidence_strength,
        status=EvidenceStatus.DRAFT,
        summary=summary,
        sample_size=sample_size,
        population=population,
        source_generated=False,
        human_reviewed=False,
    )
    db.add(evidence)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="evidence.created",
        resource_type="evidence",
        resource_id=evidence.id,
        new_value={"study_type": evidence.study_type, "status": evidence.status.value},
    )
    db.commit()
    db.refresh(evidence)
    return evidence


def update_evidence(
    db: Session,
    *,
    evidence: Evidence,
    actor_user_id: UUID,
    **fields,
) -> Evidence:
    old_value = {"summary": evidence.summary, "evidence_strength": evidence.evidence_strength.value}

    new_document_id = fields.get("document_id", evidence.document_id)
    new_chunk_id = fields.get("document_chunk_id", evidence.document_chunk_id)
    if "document_id" in fields or "document_chunk_id" in fields:
        _validate_provenance_chain(
            db,
            organization_id=evidence.organization_id,
            source_id=evidence.source_id,
            document_id=new_document_id,
            document_chunk_id=new_chunk_id,
        )

    for field_name, value in fields.items():
        if value is None:
            continue
        setattr(evidence, field_name, value)

    db.flush()
    record_audit_log(
        db,
        organization_id=evidence.organization_id,
        user_id=actor_user_id,
        action="evidence.updated",
        resource_type="evidence",
        resource_id=evidence.id,
        old_value=old_value,
        new_value={"summary": evidence.summary, "evidence_strength": evidence.evidence_strength.value},
    )
    db.commit()
    db.refresh(evidence)
    return evidence


def review_evidence(
    db: Session,
    *,
    evidence: Evidence,
    status: EvidenceStatus,
    evidence_strength,
    note: str | None,
    actor_user_id: UUID,
) -> Evidence:
    """The one path that transitions an Evidence row's review status.
    Always sets human_reviewed=True, same principle as Claim.review_claim
    (section 44). Recomputes the aggregate of every Claim linked to this
    Evidence afterward, since VERIFIED-ness is exactly the gate
    recompute_claim_aggregate uses to decide which links count."""
    from app.services.claim_evidence_service import recompute_claim_aggregate

    old_value = {"status": evidence.status.value, "human_reviewed": evidence.human_reviewed}

    evidence.status = status
    evidence.human_reviewed = True
    if evidence_strength is not None:
        evidence.evidence_strength = evidence_strength

    db.flush()
    record_audit_log(
        db,
        organization_id=evidence.organization_id,
        user_id=actor_user_id,
        action="evidence.reviewed",
        resource_type="evidence",
        resource_id=evidence.id,
        old_value=old_value,
        new_value={"status": evidence.status.value, "note": note},
    )
    db.commit()
    db.refresh(evidence)

    for link in list(evidence.claim_links):
        recompute_claim_aggregate(db, claim_id=link.claim_id, actor_user_id=actor_user_id)

    return evidence
