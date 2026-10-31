"""Provenance: one page of a knowledge object's claims, with every evidence
link, evidence row, source and document behind them, read with a fixed number
of queries however many claims or links the page holds (Rule 17)."""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.claim_evidence import ClaimEvidence
from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.evidence import Evidence
from app.models.source import Source
from app.services import claim_service, knowledge_service


def get_knowledge_provenance(db: Session, *, ko_id: UUID, org_id: UUID, limit: int, offset: int) -> dict:
    ko = knowledge_service.get_knowledge_object_or_404(
        db, object_id=ko_id, organization_id=org_id
    )
    claims, total = claim_service.list_claims(
        db,
        organization_id=org_id,
        knowledge_object_id=ko_id,
        status=None,
        limit=limit,
        offset=offset,
    )

    links = []
    if claims:
        links = db.execute(
            select(ClaimEvidence)
            .where(
                ClaimEvidence.organization_id == org_id,
                ClaimEvidence.claim_id.in_([c.id for c in claims]),
            )
            .order_by(ClaimEvidence.created_at, ClaimEvidence.id)
        ).scalars().all()

    evidence = []
    if links:
        evidence = db.execute(
            select(Evidence).where(
                Evidence.organization_id == org_id,
                Evidence.id.in_({link.evidence_id for link in links}),
            )
        ).scalars().all()

    sources = []
    if evidence:
        sources = db.execute(
            select(Source).where(
                Source.organization_id == org_id,
                Source.id.in_({e.source_id for e in evidence}),
            )
        ).scalars().all()

    documents = []
    document_ids = {e.document_id for e in evidence if e.document_id}
    if document_ids:
        # At most one current conversion per document (uq_document_conversions_one_current),
        # so the outer join cannot duplicate documents.
        documents = db.execute(
            select(Document, DocumentConversion.converter_version)
            .outerjoin(DocumentConversion, and_(DocumentConversion.document_id == Document.id,
                                                DocumentConversion.is_current))
            .where(Document.organization_id == org_id, Document.id.in_(document_ids))
        ).all()

    links_by_claim: dict[UUID, list] = {}
    for link in links:
        links_by_claim.setdefault(link.claim_id, []).append({
            "link_id": link.id, "evidence_id": link.evidence_id, "relation": link.relation, "weight": link.weight,
        })

    return {
        "knowledge_object": {"id": ko.id, "canonical_name": ko.canonical_name, "status": ko.status},
        "claims": [
            {
                "id": c.id,
                "predicate": c.predicate,
                "object_value": c.object_value,
                "text": " ".join(v for v in (c.predicate, c.object_value) if v),
                "status": c.status,
                "evidence_strength": c.evidence_strength,
                "links": links_by_claim.get(c.id, []),
            }
            for c in claims
        ],
        "evidence": {
            e.id: {
                "id": e.id, "status": e.status, "directness": e.directness, "basis": e.basis,
                "subject_tested": e.subject_tested, "summary": e.summary, "source_id": e.source_id,
                "document_id": e.document_id, "chunk_id": e.document_chunk_id, "page_number": e.page_number,
            }
            for e in evidence
        },
        "sources": {
            s.id: {"id": s.id, "title": s.title, "doi": s.doi, "full_text_accessed": s.full_text_accessed}
            for s in sources
        },
        "documents": {
            d.id: {"id": d.id, "title": d.title, "mime_type": d.mime_type, "converter_version": version}
            for d, version in documents
        },
        "total_claims": total,
        "total_evidence": len(evidence),
    }
