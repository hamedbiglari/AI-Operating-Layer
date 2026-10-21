"""Validator + Reconciler for Knowledge Transfer Packages (prompt v5 §21-25, §35, §51-53; ADR-134).

Worker output -> VALIDATOR -> RECONCILER -> canonical state, deterministically and without a model:

Validation (per item, never all-or-nothing unless the package itself is unreadable or truncated):
  * the package parses as KTP v1 (unknown keys refused) and was not cut off by the output limit;
  * every claim names an entity that exists in the topic, and has at least one usable evidence item;
  * every evidence item's source/document/element belongs to the tenant and to each other;
  * the quote is found verbatim (whitespace- and case-insensitive) in text the system actually holds for that
    source — a quote it cannot find is a citation mismatch, and a source with no stored text cannot have been
    read, so nothing is accepted from it;
  * an indirect route, or evidence about a different substance, cannot be filed as direct (§35).

Reconciliation against the existing claims of the topic:
  * same subject + predicate + object  -> DUPLICATE: no second claim; the new evidence is linked to the
    existing one (one canonical claim + N evidence links, §23);
  * same subject + predicate, different object -> VARIANT: kept as its own draft claim and pointed at the
    claim(s) it differs from, for review — it may be a refinement or a contradiction, and the system does not
    decide which;
  * otherwise -> NEW claim.
  Evidence that contradicts a claim is linked as `contradicts` and the pair is recorded as an evidence conflict
  (ADR-110); nothing is overwritten and no side is chosen (§25).

Everything created is DRAFT and `source_generated`: a worker never writes approved knowledge (§51). Evidence is
deduplicated on (source, document, quote) so the same finding reported twice is one row. The whole package is
idempotent by hash.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.document import Document
from app.models.entity import Entity
from app.models.enums import (ClaimEvidenceStrength, ClaimStatus, EvidenceDirectness, EvidenceRelation,
                              EvidenceStatus, EvidenceStrength)
from app.models.evidence import Evidence
from app.models.knowledge_transfer import KnowledgeTransferRecord
from app.models.source import Source
from app.schemas.knowledge_transfer import EVIDENCE_ROUTES, KnowledgeTransferPackage, KTPClaim, KTPEvidence
from app.services import conflict_service
from app.services.audit import record_audit_log
from app.services.evidence_service import _element_location, _validate_provenance_chain
from app.services.knowledge_service import get_knowledge_object_or_404

DIRECT_ROUTES = ("direct_subject", "general")
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _norm(text: str | None) -> str:
    """NFC, case-folded, whitespace collapsed. Used for matching only; stored text is never altered."""
    return " ".join(unicodedata.normalize("NFC", text or "").casefold().split())


def _hash(organization_id: UUID, knowledge_object_id: UUID, raw: str) -> str:
    return hashlib.sha256(f"{organization_id}|{knowledge_object_id}|{raw}".encode()).hexdigest()


def _entities(db: Session, organization_id: UUID, knowledge_object_id: UUID) -> dict[str, Entity]:
    names: dict[str, Entity] = {}
    for e in db.execute(select(Entity).where(Entity.organization_id == organization_id,
                                             Entity.knowledge_object_id == knowledge_object_id)).scalars():
        for n in [e.canonical_name, *[a for a in (e.aliases or []) if isinstance(a, str)]]:
            names.setdefault(_norm(n), e)
    return names


def _texts(db: Session, organization_id: UUID, ev: KTPEvidence) -> list[tuple[str, str]]:
    """(basis, text) the system actually holds for this evidence's source."""
    source = db.get(Source, ev.source_id)
    out: list[tuple[str, str]] = []
    docs = ([db.get(Document, ev.document_id)] if ev.document_id else
            db.execute(select(Document).where(Document.organization_id == organization_id,
                                              Document.source_id == ev.source_id)).scalars().all())
    for d in docs:
        if d is not None and d.content:
            out.append(("full_text" if source.full_text_accessed else "partial_text", d.content))
    if source.abstract:
        out.append(("abstract", source.abstract))
    return out


def _check_evidence(db: Session, organization_id: UUID, claim: KTPClaim, ev: KTPEvidence,
                    subject_names: set[str]) -> tuple[str | None, dict]:
    """Returns (rejection code or None, facts to store)."""
    try:
        _validate_provenance_chain(db, organization_id=organization_id, source_id=ev.source_id,
                                   document_id=ev.document_id, document_chunk_id=None)
        location = _element_location(db, organization_id=organization_id, document_id=ev.document_id,
                                     document_element_id=ev.document_element_id)
    except HTTPException as exc:
        return "SOURCE_REFERENCE_INVALID", {"detail": str(exc.detail)}
    if ev.route is not None and ev.route not in EVIDENCE_ROUTES:
        return "UNKNOWN_ROUTE", {"route": ev.route}
    if ev.directness == "direct" and ev.route is not None and ev.route not in DIRECT_ROUTES:
        return "INDIRECT_ROUTE_MARKED_DIRECT", {"route": ev.route}
    if ev.directness == "direct" and ev.about and _norm(ev.about) not in subject_names:
        # §35: evidence about mannitol is not evidence about Toranjebin unless labelled as such.
        return "EVIDENCE_ABOUT_OTHER_ENTITY_MARKED_DIRECT", {"about": ev.about}
    texts = _texts(db, organization_id, ev)
    if not texts:
        return "SOURCE_TEXT_UNAVAILABLE", {}
    q = _norm(ev.quote)
    basis = next((b for b, t in texts if q in _norm(t)), None)
    if basis is None:
        return "CITATION_MISMATCH", {"searched": [b for b, _ in texts]}
    return None, {"basis": basis, "location": location}


def _evidence_row(db: Session, organization_id: UUID, ev: KTPEvidence, facts: dict, record_id: UUID) -> tuple[Evidence, bool]:
    existing = db.execute(select(Evidence).where(
        Evidence.organization_id == organization_id, Evidence.source_id == ev.source_id,
        Evidence.document_id.is_(None) if ev.document_id is None else Evidence.document_id == ev.document_id,
        Evidence.summary == ev.quote)).scalars().first()
    if existing is not None:
        return existing, False
    location = facts.get("location")
    row = Evidence(
        organization_id=organization_id, source_id=ev.source_id, document_id=ev.document_id,
        document_element_id=ev.document_element_id, page_number=(location or {}).get("page") or ev.page,
        location=location, study_type=ev.study_type, directness=EvidenceDirectness(ev.directness),
        evidence_strength=EvidenceStrength.VERY_LOW, status=EvidenceStatus.DRAFT, summary=ev.quote,
        sample_size=ev.sample_size, population=ev.population, evidence_route=ev.route, evidence_about=ev.about,
        basis=facts["basis"] if facts["basis"] in ("full_text", "abstract") else None,
        # machine extraction is never certain (DB CHECK ck_evidence_machine_extraction_is_not_certain)
        extraction_confidence=min(ev.confidence, 0.99) if ev.confidence is not None else None,
        extraction_note=f"knowledge transfer package {record_id}; quote verified in {facts['basis']}",
        source_generated=True, human_reviewed=False)
    db.add(row)
    db.flush()
    return row, True


def _link(db: Session, organization_id: UUID, claim: Claim, evidence: Evidence, relation: str) -> bool:
    if db.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id,
                                              ClaimEvidence.evidence_id == evidence.id)).scalar_one_or_none():
        return False
    db.add(ClaimEvidence(organization_id=organization_id, claim_id=claim.id, evidence_id=evidence.id,
                         relation=EvidenceRelation(relation)))
    db.flush()
    return True


def _object_key(c: Claim) -> str:
    return f"e:{c.object_entity_id}" if c.object_entity_id else f"v:{_norm(c.object_value)}"


def ingest(db: Session, *, organization_id: UUID, knowledge_object_id: UUID, raw: str, submitted_by: str,
           execution_id: UUID | None = None, job_key: str | None = None, item_key: str | None = None,
           truncated: bool = False, actor_user_id: UUID | None = None) -> KnowledgeTransferRecord:
    get_knowledge_object_or_404(db, object_id=knowledge_object_id, organization_id=organization_id)
    h = _hash(organization_id, knowledge_object_id, raw)
    existing = db.execute(select(KnowledgeTransferRecord).where(
        KnowledgeTransferRecord.organization_id == organization_id,
        KnowledgeTransferRecord.package_hash == h)).scalar_one_or_none()
    if existing is not None:
        return existing                                     # idempotent: at-least-once delivery is safe
    rec = KnowledgeTransferRecord(organization_id=organization_id, knowledge_object_id=knowledge_object_id,
                                  submitted_by=submitted_by, execution_id=execution_id, job_key=job_key,
                                  item_key=item_key, package_hash=h, raw=raw, status="invalid")

    def invalid(reason: str, details: dict | None = None) -> KnowledgeTransferRecord:
        rec.status, rec.invalid_reason, rec.validation = "invalid", reason[:500], details or {}
        db.add(rec)
        db.commit()
        return rec

    if truncated:
        # §17: a cut-off package may have lost claims or evidence at its tail; it is kept for a resume, not used.
        return invalid("OUTPUT_TRUNCATED: the model stopped at its output limit")
    try:
        pkg = KnowledgeTransferPackage.model_validate(json.loads(_FENCE.sub("", raw)))
    except (ValueError, ValidationError) as exc:
        errors = exc.errors(include_input=False) if isinstance(exc, ValidationError) else [{"msg": str(exc)[:300]}]
        return invalid("MALFORMED: not a valid Knowledge Transfer Package v1",
                       {"errors": json.loads(json.dumps(errors, default=str))[:50]})
    # Parsed: provisional status until reconciliation decides (set again below).
    rec.ktp_version, rec.status = pkg.ktp_version, "nothing_accepted"
    db.add(rec)
    db.flush()

    names = _entities(db, organization_id, knowledge_object_id)
    existing_claims = db.execute(select(Claim).where(Claim.organization_id == organization_id,
                                                     Claim.knowledge_object_id == knowledge_object_id)).scalars().all()
    validation, outcomes, candidates, conflict_claims = [], [], [], set()
    for c in pkg.claims:
        verdict: dict = {"local_id": c.local_id, "rejected_evidence": []}
        subject = names.get(_norm(c.subject))
        obj_entity = names.get(_norm(c.object_entity)) if c.object_entity else None
        reason = None
        if subject is None:
            reason = "UNKNOWN_ENTITY"
            candidates.append(c.subject)
        elif c.object_entity and obj_entity is None:
            reason = "UNKNOWN_OBJECT_ENTITY"
            candidates.append(c.object_entity)
        elif (c.object_value is None) == (c.object_entity is None):
            reason = "OBJECT_REQUIRED"         # exactly one of object_value / object_entity (DB CHECK too)
        elif not c.evidence:
            reason = "UNSUPPORTED_ASSERTION"
        accepted: list[tuple[KTPEvidence, dict]] = []
        if reason is None:
            subject_names = {_norm(subject.canonical_name), *(_norm(a) for a in (subject.aliases or []) if isinstance(a, str))}
            for i, ev in enumerate(c.evidence):
                code, facts = _check_evidence(db, organization_id, c, ev, subject_names)
                if code:
                    verdict["rejected_evidence"].append({"index": i, "code": code, **facts})
                else:
                    accepted.append((ev, facts))
            if not accepted:
                reason = "NO_VERIFIABLE_EVIDENCE"
        verdict["accepted"] = reason is None
        verdict["reason"] = reason
        validation.append(verdict)
        if reason is not None:
            continue

        key = f"e:{obj_entity.id}" if obj_entity else f"v:{_norm(c.object_value)}"
        same_pred = [x for x in existing_claims
                     if x.subject_entity_id == subject.id and _norm(x.predicate) == _norm(c.predicate)]
        match = next((x for x in same_pred if _object_key(x) == key), None)
        if match is not None:
            claim, kind, variant_of = match, "duplicate", []
        else:
            claim = Claim(organization_id=organization_id, knowledge_object_id=knowledge_object_id,
                          subject_entity_id=subject.id, predicate=c.predicate,
                          object_entity_id=obj_entity.id if obj_entity else None,
                          object_value=None if obj_entity else c.object_value, section_key=c.section_key,
                          claim_type=c.claim_type, status=ClaimStatus.DRAFT,
                          evidence_strength=ClaimEvidenceStrength.UNVERIFIED, source_generated=True,
                          human_reviewed=False)
            db.add(claim)
            db.flush()
            existing_claims.append(claim)
            variant_of = [str(x.id) for x in same_pred]
            kind = "variant" if variant_of else "new_claim"
        new_evidence, new_links, relations = 0, 0, set()
        for ev, facts in accepted:
            row, created = _evidence_row(db, organization_id, ev, facts, rec.id)
            new_evidence += created
            new_links += _link(db, organization_id, claim, row, ev.relation)
            relations.add(ev.relation)
        if kind == "duplicate" and new_links == 0:
            kind = "no_new_evidence"
        if "contradicts" in relations or (kind in ("duplicate", "no_new_evidence") and "supports" in relations):
            conflict_claims.add(claim.id)
        outcomes.append({"local_id": c.local_id, "outcome": kind, "claim_id": str(claim.id),
                         "variant_of": variant_of, "finding_kind": c.finding_kind,
                         "evidence_created": new_evidence, "links_created": new_links})

    accepted_n = sum(v["accepted"] for v in validation)
    rejected_any = accepted_n < len(validation) or any(v["rejected_evidence"] for v in validation)
    rec.status = ("nothing_accepted" if accepted_n == 0 else "partially_reconciled" if rejected_any else "reconciled")
    rec.validation = {"claims": validation}
    rec.reconciliation = {"claims": outcomes, "entity_candidates": sorted(set(candidates)),
                          "open_questions": pkg.open_questions, "gaps": pkg.gaps, "assumptions": pkg.assumptions,
                          "rejected_interpretations": pkg.rejected_interpretations,
                          "processing_status": pkg.processing_status}
    record_audit_log(db, organization_id=organization_id, user_id=actor_user_id, action="knowledge_transfer.reconciled",
                     resource_type="knowledge_transfer_package", resource_id=rec.id,
                     new_value={"status": rec.status, "accepted_claims": accepted_n, "submitted_by": submitted_by})
    db.commit()
    conflicts = []
    for claim_id in conflict_claims:
        # Records every supports/contradicts pair on the claim that is not on file yet (commits; ADR-110).
        conflicts += [str(x.id) for x in conflict_service.detect(db, organization_id=organization_id, claim_id=claim_id)]
    if conflicts:
        rec.reconciliation = {**rec.reconciliation, "conflicts_recorded": conflicts}
        db.commit()
    db.refresh(rec)
    return rec
