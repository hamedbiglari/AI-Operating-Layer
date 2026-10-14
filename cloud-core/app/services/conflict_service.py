"""
Conflict intelligence (ADR-110, §21).

When two reviewed findings disagree about the same claim the system records the disagreement as an object
with the comparison a person needs, and never chooses a side on its own. Resolving or declaring a conflict
unresolvable requires a written reason (enforced by the database too).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence import Evidence
from app.models.evidence_conflict import COMPARISON_FIELDS, CONFLICT_STATES, EvidenceConflict
from app.models.source import Source
from app.services.audit import record_audit_log

OPEN_STATES = ("unreviewed", "under_review", "partially_resolved")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compare(db: Session, a: Evidence, b: Evidence) -> dict:
    """The side-by-side a reviewer needs. Only facts that are recorded; nothing is inferred."""
    def side(e: Evidence) -> dict:
        src = db.get(Source, e.source_id)
        return {"evidence_id": str(e.id), "population": e.population, "sample_size": e.sample_size,
                "study_design": e.study_type, "directness": e.directness.value, "route": e.evidence_route,
                "about": e.evidence_about, "basis": e.basis,
                "extraction_confidence": float(e.extraction_confidence) if e.extraction_confidence is not None else None,
                "evidence_strength": e.evidence_strength.value,
                "source_title": src.title if src else None,
                "publication_date": src.publication_date.isoformat() if src and src.publication_date else None,
                "full_text_read": bool(src and src.full_text_accessed)}
    sa, sb = side(a), side(b)
    differs = sorted(k for k in ("population", "sample_size", "study_design", "directness", "route",
                                 "publication_date") if sa.get(k) != sb.get(k))
    unknown = sorted(k for k in COMPARISON_FIELDS if sa.get(k) is None and sb.get(k) is None)
    return {"supporting": sa, "contradicting": sb, "differs_on": differs, "not_recorded": unknown}


def detect(db: Session, *, organization_id: UUID, claim_id: UUID) -> list[EvidenceConflict]:
    """Create a conflict row for every supports/contradicts pair on this claim that is not recorded yet."""
    claim = db.execute(select(Claim).where(Claim.id == claim_id, Claim.organization_id == organization_id)).scalar_one_or_none()
    if claim is None:
        raise HTTPException(404, "Claim not found.")
    links = db.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim_id)).scalars().all()
    rel = lambda l: str(getattr(l.relation, "value", l.relation))  # noqa: E731
    supports = [l.evidence_id for l in links if rel(l) == "supports"]
    against = [l.evidence_id for l in links if rel(l) == "contradicts"]
    made = []
    for s in supports:
        for c in against:
            exists = db.execute(select(EvidenceConflict).where(
                EvidenceConflict.organization_id == organization_id, EvidenceConflict.claim_id == claim_id,
                EvidenceConflict.supporting_evidence_id == s, EvidenceConflict.contradicting_evidence_id == c)).scalar_one_or_none()
            if exists:
                continue
            ea, eb = db.get(Evidence, s), db.get(Evidence, c)
            row = EvidenceConflict(organization_id=organization_id, claim_id=claim_id,
                                   knowledge_object_id=claim.knowledge_object_id, supporting_evidence_id=s,
                                   contradicting_evidence_id=c, status="unreviewed", comparison=_compare(db, ea, eb))
            db.add(row)
            made.append(row)
    db.commit()
    return made


def out(c: EvidenceConflict) -> dict:
    return {"id": str(c.id), "claim_id": str(c.claim_id), "status": c.status,
            "knowledge_object_id": str(c.knowledge_object_id) if c.knowledge_object_id else None,
            "supporting_evidence_id": str(c.supporting_evidence_id),
            "contradicting_evidence_id": str(c.contradicting_evidence_id),
            "comparison": c.comparison, "resolution_note": c.resolution_note,
            "reviewed_at": c.reviewed_at, "created_at": c.created_at,
            "note": "Both findings stay on the record. The system does not choose between them."}


def review(db: Session, *, organization_id: UUID, conflict_id: UUID, status: str, note: str | None,
           actor_user_id: UUID) -> dict:
    if status not in CONFLICT_STATES:
        raise HTTPException(422, f"status must be one of: {', '.join(CONFLICT_STATES)}")
    c = db.execute(select(EvidenceConflict).where(EvidenceConflict.id == conflict_id,
                                                  EvidenceConflict.organization_id == organization_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Conflict not found.")
    if status in ("resolved", "unresolvable", "partially_resolved") and not (note or "").strip():
        raise HTTPException(422, "Say why — a resolution needs a written reason.")
    c.status = status
    c.resolution_note = (note or "").strip() or None
    c.reviewed_by_user_id = actor_user_id
    c.reviewed_at = _now()
    record_audit_log(db, organization_id=organization_id, user_id=actor_user_id, action="evidence_conflict.reviewed",
                     resource_type="evidence_conflict", resource_id=c.id, new_value={"status": status})
    db.commit()
    db.refresh(c)
    return out(c)


def list_conflicts(db: Session, *, organization_id: UUID, status: str | None, claim_id: UUID | None,
                   knowledge_object_id: UUID | None, limit: int, offset: int, sort=None) -> tuple[int, list[EvidenceConflict]]:
    from sqlalchemy import func

    from app.schemas.common import SortDirection, apply_sort

    stmt = select(EvidenceConflict).where(EvidenceConflict.organization_id == organization_id)
    if status:
        stmt = stmt.where(EvidenceConflict.status == status)
    if claim_id:
        stmt = stmt.where(EvidenceConflict.claim_id == claim_id)
    if knowledge_object_id:
        stmt = stmt.where(EvidenceConflict.knowledge_object_id == knowledge_object_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, EvidenceConflict, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return total, rows
