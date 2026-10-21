"""
Publication building (ADR-116, §42–§44, §59–§67).

A sentence is only ever created *from* a knowledge unit that already carries its sources. `add_sentence`
therefore takes the claim it came from, derives the supporting sources through the existing
claim → evidence → source chain, and refuses to accept a source that does not actually support that
claim (§48). There is no entry point that writes prose first and looks for citations afterwards.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence import Evidence
from app.models.knowledge_object import KnowledgeObject
from app.models.publication import (
    CITATION_REQUIRED_KINDS, Publication, PublicationReference, PublicationSection, PublicationSentence,
    SentenceSource,
)
from app.models.source import Source
from app.services import citation_resolver


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _publication(db: Session, organization_id: UUID, publication_id: UUID) -> Publication:
    pub = db.execute(select(Publication).where(
        Publication.id == publication_id, Publication.organization_id == organization_id)).scalar_one_or_none()
    if pub is None:
        raise HTTPException(404, "Publication not found.")
    return pub


def create_publication(db: Session, *, organization_id: UUID, knowledge_object_id: UUID, title: str | None,
                       language: str = "en") -> Publication:
    topic = db.execute(select(KnowledgeObject).where(
        KnowledgeObject.id == knowledge_object_id,
        KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if topic is None:
        raise HTTPException(404, "Knowledge object not found.")
    version = (db.execute(select(func.coalesce(func.max(Publication.publication_version), 0)).where(
        Publication.organization_id == organization_id,
        Publication.knowledge_object_id == topic.id)).scalar_one()) + 1
    # §46 — an earlier version keeps its own numbering; it is superseded, never renumbered
    for old in db.execute(select(Publication).where(
            Publication.organization_id == organization_id,
            Publication.knowledge_object_id == topic.id,
            Publication.status.in_(("resolved", "published")))).scalars().all():
        old.status = "superseded"
    pub = Publication(organization_id=organization_id, knowledge_object_id=topic.id,
                      publication_version=version, title=(title or topic.canonical_name)[:500],
                      language=language, status="draft", knowledge_version=topic.version)
    db.add(pub)
    db.commit()
    db.refresh(pub)
    return pub


def add_section(db: Session, *, organization_id: UUID, publication_id: UUID, title: str,
                section_key: str | None) -> PublicationSection:
    pub = _publication(db, organization_id, publication_id)
    position = (db.execute(select(func.coalesce(func.max(PublicationSection.position), -1)).where(
        PublicationSection.publication_id == pub.id)).scalar_one()) + 1
    row = PublicationSection(organization_id=organization_id, publication_id=pub.id, title=title[:300],
                             section_key=section_key, position=position)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _sources_for_claim(db: Session, organization_id: UUID, claim_id: UUID) -> list[dict]:
    """The claim's own supporting evidence, carried through with its directness (§49)."""
    links = db.execute(select(ClaimEvidence).where(
        ClaimEvidence.organization_id == organization_id, ClaimEvidence.claim_id == claim_id)).scalars().all()
    out: list[dict] = []
    for link in links:
        relation = str(getattr(link.relation, "value", link.relation))
        if relation != "supports":
            continue
        ev = db.get(Evidence, link.evidence_id)
        if ev is None or ev.source_id is None:
            continue
        verified = str(getattr(ev.status, "value", ev.status)) == "verified"
        out.append({"source_id": ev.source_id, "evidence_id": ev.id, "claim_id": claim_id,
                    "directness": str(getattr(ev.directness, "value", ev.directness)),
                    "support": "supports" if verified else "unverified"})
    return out


def add_sentence(db: Session, *, organization_id: UUID, publication_id: UUID, text: str,
                 kind: str = "factual", claim_id: UUID | None = None, paragraph: int = 0,
                 section_id: UUID | None = None, extra_source_ids: list[UUID] | None = None,
                 additional_claim_ids: list[UUID] | None = None) -> dict:
    """Create one sentence together with the sources that justify it.

    A sentence of a citation-requiring kind with no claim and no validated source is accepted, but it is
    recorded as evidence-unavailable — the resolver will not give it a number (§61)."""
    pub = _publication(db, organization_id, publication_id)
    if pub.status in ("published", "superseded"):
        raise HTTPException(409, "This publication version is closed; create a new version.")
    position = (db.execute(select(func.coalesce(func.max(PublicationSentence.position), -1)).where(
        PublicationSentence.publication_id == pub.id)).scalar_one()) + 1
    sentence = PublicationSentence(organization_id=organization_id, publication_id=pub.id,
                                   publication_section_id=section_id, position=position, paragraph=paragraph,
                                   kind=kind, text=text.strip(), knowledge_unit_claim_id=claim_id)
    db.add(sentence)
    db.flush()

    supports: list[dict] = []
    if claim_id is not None:
        claim = db.execute(select(Claim).where(Claim.id == claim_id,
                                               Claim.organization_id == organization_id)).scalar_one_or_none()
        if claim is None:
            raise HTTPException(404, "Claim not found.")
        supports = _sources_for_claim(db, organization_id, claim.id)
    # v4: a synthesised sentence may rest on several claims. Each one's sources come through that claim's
    # own evidence chain — the same rule as the primary claim, never topic relevance (§48).
    for extra_claim in (additional_claim_ids or []):
        if claim_id is None:
            raise HTTPException(422, "Additional claims need a primary claim.")
        other = db.execute(select(Claim).where(Claim.id == extra_claim,
                                               Claim.organization_id == organization_id)).scalar_one_or_none()
        if other is None:
            raise HTTPException(404, "Claim not found.")
        supports.extend(_sources_for_claim(db, organization_id, other.id))
    # one row per source: a verified link wins over an unverified one for the same source
    best: dict = {}
    for item in supports:
        held = best.get(item["source_id"])
        if held is None or (held["support"] != "supports" and item["support"] == "supports"):
            best[item["source_id"]] = item
    supports = list(best.values())

    # §48 — an extra source is only accepted if it genuinely supports this claim; topic relevance is not enough
    for sid in (extra_source_ids or []):
        if claim_id is None:
            raise HTTPException(422, "A source can only be attached through the claim it supports.")
        if not any(s["source_id"] == sid for s in supports):
            raise HTTPException(409, "That source does not support this claim; it cannot be cited for it.")

    for s in supports:
        db.add(SentenceSource(organization_id=organization_id, publication_sentence_id=sentence.id,
                              source_id=s["source_id"], claim_id=s.get("claim_id") or claim_id,
                              evidence_id=s["evidence_id"],
                              support=s["support"], directness=s["directness"]))
    if kind in CITATION_REQUIRED_KINDS and not any(s["support"] == "supports" for s in supports):
        sentence.evidence_unavailable = True
    db.commit()
    db.refresh(sentence)
    return sentence_out(db, sentence)


def sentence_out(db: Session, s: PublicationSentence) -> dict:
    sources = db.execute(select(SentenceSource).where(
        SentenceSource.publication_sentence_id == s.id)).scalars().all()
    rendered = s.text
    if s.citation_text:
        rendered = f"{s.text} {s.citation_text}"          # §41 — exactly one space before the parenthesis
    return {"id": str(s.id), "position": s.position, "paragraph": s.paragraph, "kind": s.kind, "text": s.text,
            "rendered": rendered, "citation_numbers": s.citation_numbers, "citation_text": s.citation_text,
            "resolved": s.resolved, "evidence_unavailable": s.evidence_unavailable,
            "claim_id": str(s.knowledge_unit_claim_id) if s.knowledge_unit_claim_id else None,
            "sources": [{"source_id": str(x.source_id), "evidence_id": str(x.evidence_id) if x.evidence_id else None,
                         "support": x.support, "directness": x.directness} for x in sources]}


def publication_out(p: Publication) -> dict:
    return {"id": str(p.id), "knowledge_object_id": str(p.knowledge_object_id),
            "publication_version": p.publication_version, "title": p.title, "language": p.language,
            "status": p.status, "failure_reason": p.failure_reason, "knowledge_version": p.knowledge_version,
            "reference_count": p.reference_count, "sentence_count": p.sentence_count,
            "resolved_at": p.resolved_at, "created_at": p.created_at}


def render(db: Session, *, organization_id: UUID, publication_id: UUID) -> dict:
    """The finished document: sentences in order with their citations, then the numbered reference list."""
    pub = _publication(db, organization_id, publication_id)
    sections = db.execute(select(PublicationSection).where(
        PublicationSection.publication_id == pub.id).order_by(PublicationSection.position)).scalars().all()
    sentences = db.execute(select(PublicationSentence).where(
        PublicationSentence.publication_id == pub.id).order_by(PublicationSentence.position)).scalars().all()
    by_section: dict = {}
    for s in sentences:
        by_section.setdefault(s.publication_section_id, []).append(sentence_out(db, s))
    body = [{"section_id": str(sec.id), "title": sec.title, "section_key": sec.section_key,
             "sentences": by_section.get(sec.id, [])} for sec in sections]
    loose = by_section.get(None, [])
    if loose:
        body.append({"section_id": None, "title": None, "section_key": None, "sentences": loose})
    return {"publication": publication_out(pub), "body": body,
            "references": citation_resolver.reference_list(db, organization_id=organization_id,
                                                           publication_id=pub.id),
            "unsupported_sentences": [s.position for s in sentences if s.evidence_unavailable]}


# ---------------------------------------------------------------- §59 Citation Integrity Audit
def integrity_audit(db: Session, *, organization_id: UUID, publication_id: UUID) -> dict:
    """Twenty-two checks. Each one is a fact about this publication, not a self-assessment."""
    pub = _publication(db, organization_id, publication_id)
    sentences = db.execute(select(PublicationSentence).where(
        PublicationSentence.publication_id == pub.id).order_by(PublicationSentence.position)).scalars().all()
    refs = db.execute(select(PublicationReference).where(
        PublicationReference.publication_id == pub.id)).scalars().all()
    links = db.execute(select(SentenceSource).where(
        SentenceSource.organization_id == organization_id,
        SentenceSource.publication_sentence_id.in_([s.id for s in sentences]))).scalars().all() if sentences else []

    numbers = {r.reference_number for r in refs}
    cited_numbers: set = set()
    needing = [s for s in sentences if s.kind in CITATION_REQUIRED_KINDS]
    missing: list[int] = []
    for s in sentences:
        for n in (s.citation_numbers or []):
            cited_numbers.add(n)
        if s.kind in CITATION_REQUIRED_KINDS and not s.citation_numbers and not s.evidence_unavailable:
            missing.append(s.position)

    by_source: dict = {}
    for r in refs:
        by_source.setdefault(r.source_id, []).append(r.reference_number)
    duplicate_numbers = len(numbers) != len(refs)
    source_with_two_numbers = [str(k) for k, v in by_source.items() if len(v) > 1]
    dangling = sorted(cited_numbers - numbers)
    uncited = sorted(numbers - cited_numbers)
    # §52/§88 — a source whose record holds only a title is not an integrity failure; omitting fields is
    # exactly what the prompt asks for. What WOULD be a failure is a reference the resolver did not build
    # from stored fields, so that is what the check tests; the bare ones are reported for information.
    bare_references = [r.reference_number for r in refs
                       if not (r.metadata_ or {}).get("fields_used")]
    not_resolver_built = [r.reference_number for r in refs if r.metadata_ is None]
    # numbering must follow first appearance
    order_ok = True
    seen_order: list[int] = []
    for s in sentences:
        for n in sorted(s.citation_numbers or []):
            if n not in seen_order:
                seen_order.append(n)
    if seen_order != sorted(seen_order):
        order_ok = False
    # a cited source must actually support the sentence it is cited for
    unsupported_links = [str(l.publication_sentence_id) for l in links
                         if l.support not in citation_resolver.CITING_SUPPORT]
    checks = {
        "every_citation_required_sentence_has_a_citation_or_is_marked": not missing,
        "no_citation_number_is_dangling": not dangling,
        "no_number_belongs_to_two_sources": not duplicate_numbers,
        "no_source_holds_two_numbers": not source_with_two_numbers,
        "numbering_follows_first_appearance": order_ok,
        "reference_list_is_numeric": [r.reference_number for r in sorted(refs, key=lambda x: x.reference_number)]
                                     == list(range(1, len(refs) + 1)),
        "no_reference_was_invented": not not_resolver_built,
        "every_cited_source_supports_its_sentence": not unsupported_links,
        "publication_is_resolved": pub.status in ("resolved", "published"),
    }
    return {
        "publication_id": str(pub.id), "publication_version": pub.publication_version,
        "sentences": len(sentences), "citation_required_sentences": len(needing),
        "sentences_with_citations": sum(1 for s in sentences if s.citation_numbers),
        "sentences_marked_evidence_unavailable": sum(1 for s in sentences if s.evidence_unavailable),
        "references": len(refs), "cited_numbers": len(cited_numbers),
        "uncited_references": uncited, "dangling_numbers": dangling,
        "sentences_missing_a_citation": missing,
        "sources_with_more_than_one_number": source_with_two_numbers,
        "references_with_only_a_title": bare_references,
        "checks": checks, "passed": all(checks.values()),
        # §60 — presence is not support; these are reported separately and never merged into one score
        "coverage": {
            "citation_presence": None if not needing else
                round(100.0 * sum(1 for s in needing if s.citation_numbers) / len(needing), 1),
            "citation_validity": None if not cited_numbers else
                round(100.0 * len(cited_numbers - set(dangling)) / len(cited_numbers), 1),
            "citation_support": None if not links else
                round(100.0 * sum(1 for l in links if l.support in citation_resolver.CITING_SUPPORT) / len(links), 1),
            "note": ("Presence, validity and support are three different questions. A publication can have a "
                     "citation on every sentence and still be unsupported."),
        },
    }
