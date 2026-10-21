"""
Deterministic questions the command workspace can answer straight from the knowledge base (prompt v4.0
§54; ADR-125). No model is involved in any of these, so none of them costs anything or can invent a
result — they are joins over provenance that already exists.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence import Evidence
from app.models.evidence_conflict import EvidenceConflict
from app.models.knowledge_object import KnowledgeObject
from app.models.knowledge_schema import KnowledgeSection, SectionDefinition, SectionPropagation
from app.models.publication import Publication, PublicationSentence


def _v(x):
    return str(getattr(x, "value", x)) if x is not None else None


def claims_on_page(db: Session, *, organization_id: UUID, document_id: UUID, page: int) -> dict:
    evidence = db.execute(select(Evidence).where(
        Evidence.organization_id == organization_id, Evidence.document_id == document_id,
        Evidence.page_number == page)).scalars().all()
    by_ev = {e.id: e for e in evidence}
    links = db.execute(select(ClaimEvidence).where(
        ClaimEvidence.organization_id == organization_id,
        ClaimEvidence.evidence_id.in_(list(by_ev) or [None]))).scalars().all()
    claims = {c.id: c for c in db.execute(select(Claim).where(
        Claim.organization_id == organization_id,
        Claim.id.in_([l.claim_id for l in links] or [None]))).scalars().all()}
    without_location = db.execute(select(func.count()).select_from(Evidence).where(
        Evidence.organization_id == organization_id, Evidence.document_id == document_id,
        Evidence.page_number.is_(None))).scalar_one()
    return {"document_id": str(document_id), "page": page,
            "claims": [{"claim_id": str(l.claim_id), "predicate": claims[l.claim_id].predicate,
                        "object_value": claims[l.claim_id].object_value, "status": _v(claims[l.claim_id].status),
                        "relation": _v(l.relation), "evidence_id": str(l.evidence_id),
                        "location": by_ev[l.evidence_id].location}
                       for l in links if l.claim_id in claims],
            "evidence_on_page": len(evidence),
            "evidence_in_document_without_a_location": int(without_location),
            "note": ("Only evidence recorded with a location can be placed on a page. Evidence from this document "
                     "without one is counted above rather than silently left out.")}


def unsupported_statements(db: Session, *, organization_id: UUID, knowledge_object_id: UUID | None = None,
                           publication_id: UUID | None = None) -> dict:
    from app.services import publication_service

    if publication_id is None:
        if knowledge_object_id is None:
            raise HTTPException(422, "Name a publication or a topic.")
        pub = db.execute(select(Publication).where(
            Publication.organization_id == organization_id, Publication.knowledge_object_id == knowledge_object_id)
            .order_by(Publication.publication_version.desc()).limit(1)).scalar_one_or_none()
        if pub is None:
            return {"publication_id": None, "sentences": [],
                    "note": "This topic has no publication yet, so there are no statements to check."}
        publication_id = pub.id
    audit = publication_service.integrity_audit(db, organization_id=organization_id, publication_id=publication_id)
    rows = db.execute(select(PublicationSentence).where(
        PublicationSentence.publication_id == publication_id,
        PublicationSentence.evidence_unavailable.is_(True)).order_by(PublicationSentence.position)).scalars().all()
    return {"publication_id": str(publication_id),
            "sentences": [{"position": s.position, "text": s.text, "kind": s.kind} for s in rows],
            "sentences_missing_a_citation": audit["sentences_missing_a_citation"],
            "integrity_checks": audit["checks"], "coverage": audit["coverage"]}


def contradictions(db: Session, *, organization_id: UUID, knowledge_object_id: UUID) -> dict:
    claims = {c.id: c for c in db.execute(select(Claim).where(
        Claim.organization_id == organization_id, Claim.knowledge_object_id == knowledge_object_id)).scalars()}
    conflicts = db.execute(select(EvidenceConflict).where(
        EvidenceConflict.organization_id == organization_id,
        EvidenceConflict.claim_id.in_(list(claims) or [None]))).scalars().all()
    links = db.execute(select(ClaimEvidence).where(
        ClaimEvidence.organization_id == organization_id,
        ClaimEvidence.claim_id.in_(list(claims) or [None]))).scalars().all()
    contested = {}
    for l in links:
        contested.setdefault(l.claim_id, set()).add(_v(l.relation))
    unrecorded = [cid for cid, rels in contested.items() if {"supports", "contradicts"} <= rels
                  and not any(k.claim_id == cid for k in conflicts)]
    return {"knowledge_object_id": str(knowledge_object_id),
            "conflicts": [{"conflict_id": str(k.id), "claim_id": str(k.claim_id),
                           "claim": f"{claims[k.claim_id].predicate} {claims[k.claim_id].object_value or ''}".strip(),
                           "status": k.status, "supporting_evidence_id": str(k.supporting_evidence_id),
                           "contradicting_evidence_id": str(k.contradicting_evidence_id),
                           "differs_on": (k.comparison or {}).get("differs_on"),
                           "resolution_note": k.resolution_note} for k in conflicts],
            "claims_with_both_sides_but_no_conflict_record": [str(c) for c in unrecorded],
            "note": "The system never chooses a side; resolution is a person's written decision."}


def section_applicability(db: Session, *, organization_id: UUID, category_id: UUID, section_key: str) -> dict:
    definition = db.execute(select(SectionDefinition).where(
        SectionDefinition.organization_id == organization_id, SectionDefinition.category_id == category_id,
        SectionDefinition.key == section_key)).scalar_one_or_none()
    if definition is None:
        raise HTTPException(404, "That section is not in this category's schema.")
    topics = db.execute(select(KnowledgeObject).where(
        KnowledgeObject.organization_id == organization_id, KnowledgeObject.category_id == category_id)).scalars().all()
    cells = {c.knowledge_object_id: c for c in db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id, KnowledgeSection.section_key == section_key,
        KnowledgeSection.knowledge_object_id.in_([t.id for t in topics] or [None]))).scalars()}
    props = {p.knowledge_object_id: p for p in db.execute(select(SectionPropagation).where(
        SectionPropagation.organization_id == organization_id,
        SectionPropagation.section_definition_id == definition.id)).scalars()}
    return {"section_key": section_key, "title": definition.title, "origin": definition.origin,
            "topics": [{"knowledge_object_id": str(t.id), "name": t.canonical_name,
                        "cell_status": cells[t.id].status if t.id in cells else None,
                        "rationale": cells[t.id].rationale if t.id in cells else None,
                        "proposal_state": props[t.id].state if t.id in props else None} for t in topics],
            "note": ("A section discovered on one topic is a proposal for the others; nothing is written into a "
                     "sibling until a person decides (ADR-114).")}


def claim_evidence(db: Session, *, organization_id: UUID, claim_id: UUID) -> dict:
    claim = db.execute(select(Claim).where(Claim.id == claim_id, Claim.organization_id == organization_id)).scalar_one_or_none()
    if claim is None:
        raise HTTPException(404, "Claim not found.")
    links = db.execute(select(ClaimEvidence).where(ClaimEvidence.organization_id == organization_id,
                                                   ClaimEvidence.claim_id == claim.id)).scalars().all()
    ev = {e.id: e for e in db.execute(select(Evidence).where(Evidence.id.in_([l.evidence_id for l in links] or [None]))).scalars()}
    rows = [{"evidence_id": str(l.evidence_id), "relation": _v(l.relation), "status": _v(ev[l.evidence_id].status),
             "directness": _v(ev[l.evidence_id].directness), "strength": _v(ev[l.evidence_id].evidence_strength),
             "summary": ev[l.evidence_id].summary, "page": ev[l.evidence_id].page_number}
            for l in links if l.evidence_id in ev]
    verified_direct = [r for r in rows if r["status"] == "verified" and r["directness"] == "direct"
                       and r["relation"] == "supports"]
    return {"claim_id": str(claim.id), "claim": f"{claim.predicate} {claim.object_value or ''}".strip(),
            "evidence": rows, "verified_direct_support": len(verified_direct),
            "external_search": {"run": False,
                                "reason": ("This command reports evidence already in the knowledge base. Searching "
                                           "external providers is a research run (Research screen), which records "
                                           "every provider's result and failure.")}}
