"""
Coverage Audit (ADR-115, §17–§23).

Six dimensions, each counted from tables that already exist. Two rules shape every function here:

1. **Never collapse the dimensions.** There is no single "completeness %" anywhere in this module, because
   a topic with every section present and no evidence behind them is not 100% anything.
2. **Never report a failure as zero** (§78). A failed run is its own row; the last successful run stays
   readable and is what callers get, marked stale with the reason the newer attempt failed.

Where a figure cannot be known, it is reported as `None` with a stated reason — not as 0.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.coverage_audit import CoverageAudit
from app.models.document import Document
from app.models.evidence import Evidence
from app.models.evidence_conflict import EvidenceConflict
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_object import KnowledgeObject
from app.models.knowledge_schema import Category, KnowledgeSection, SectionDefinition, SectionPropagation
from app.models.source import Source

READ_SECTION_STATES = ("documented", "verified")
OPEN_SECTION_STATES = ("needs_research", "new", "partial", "processing")
CLOSED_SECTION_STATES = ("not_applicable", "no_evidence_found")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pct(part: int, whole: int) -> float | None:
    """A percentage only where the denominator is real. Zero sources is not 0% coverage — it is unknown."""
    return None if not whole else round(100.0 * part / whole, 1)


# ---------------------------------------------------------------- the six dimensions
def _source_dimension(db: Session, org: UUID, source_ids: list[UUID]) -> dict:
    if not source_ids:
        return {"total": 0, "accessible": 0, "percent_accessible": None,
                "note": "No sources linked to this topic yet."}
    rows = db.execute(select(Source).where(Source.organization_id == org, Source.id.in_(source_ids))).scalars().all()
    by_access: dict = {}
    by_type: dict = {}
    languages: dict = {}
    for s in rows:
        by_access[s.content_access] = by_access.get(s.content_access, 0) + 1
        t = str(getattr(s.source_type, "value", s.source_type))
        by_type[t] = by_type.get(t, 0) + 1
        lang = (s.metadata_ or {}).get("language") if s.metadata_ else None
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
    full = sum(1 for s in rows if s.full_text_accessed)
    abstract = by_access.get("abstract_only", 0)
    blocked = sum(by_access.get(k, 0) for k in ("paywalled", "registration_required", "access_blocked",
                                                "restricted", "unavailable"))
    return {"total": len(rows), "by_access": by_access, "by_type": by_type,
            "languages": languages or {"unrecorded": len(rows)},
            "full_text_read": full, "abstract_only": abstract, "inaccessible": blocked,
            "percent_full_text": _pct(full, len(rows)),
            "note": "Access states are what the system actually holds, never what it hopes to hold."}


def _processing_dimension(db: Session, org: UUID, source_ids: list[UUID]) -> dict:
    if not source_ids:
        return {"documents": 0, "percent_extracted": None, "note": "Nothing to process yet."}
    docs = db.execute(select(Document).where(Document.organization_id == org,
                                             Document.source_id.in_(source_ids))).scalars().all()
    by_status: dict = {}
    for d in docs:
        key = str(getattr(d.extraction_status, "value", d.extraction_status))
        by_status[key] = by_status.get(key, 0) + 1
    done = by_status.get("succeeded", 0) + by_status.get("completed", 0)
    failed = by_status.get("failed", 0)
    return {"documents": len(docs), "by_extraction_status": by_status, "extracted": done, "failed": failed,
            "percent_extracted": _pct(done, len(docs)),
            "sources_without_a_document": len(set(source_ids) - {d.source_id for d in docs}),
            "note": ("OCR, table, figure, audio and video coverage are not separately recorded yet; "
                     "they are reported as unavailable rather than as zero.")}


def _knowledge_dimension(db: Session, org: UUID, topic_id: UUID) -> dict:
    claims = db.execute(select(Claim).where(Claim.organization_id == org,
                                            Claim.knowledge_object_id == topic_id)).scalars().all()
    by_status: dict = {}
    for c in claims:
        key = str(getattr(c.status, "value", c.status))
        by_status[key] = by_status.get(key, 0) + 1
    reviewed = sum(1 for c in claims if c.human_reviewed)
    machine = sum(1 for c in claims if c.source_generated)
    sectioned = sum(1 for c in claims if c.section_key)
    return {"claims": len(claims), "by_status": by_status, "human_reviewed": reviewed,
            "machine_proposed": machine, "assigned_to_a_section": sectioned,
            "unassigned_to_a_section": len(claims) - sectioned,
            "percent_reviewed": _pct(reviewed, len(claims)),
            "note": "A machine-proposed claim is not knowledge until a person has reviewed it."}


def _evidence_dimension(db: Session, org: UUID, topic_id: UUID) -> dict:
    claims = db.execute(select(Claim.id).where(Claim.organization_id == org,
                                               Claim.knowledge_object_id == topic_id)).scalars().all()
    if not claims:
        return {"claims": 0, "percent_supported": None, "note": "No claims to support yet."}
    links = db.execute(select(ClaimEvidence).where(ClaimEvidence.organization_id == org,
                                                   ClaimEvidence.claim_id.in_(claims))).scalars().all()
    supported = {l.claim_id for l in links if str(getattr(l.relation, "value", l.relation)) == "supports"}
    contradicted = {l.claim_id for l in links if str(getattr(l.relation, "value", l.relation)) == "contradicts"}
    ev_ids = {l.evidence_id for l in links}
    direct = indirect = verified = 0
    if ev_ids:
        for e in db.execute(select(Evidence).where(Evidence.id.in_(ev_ids))).scalars().all():
            if str(getattr(e.status, "value", e.status)) == "verified":
                verified += 1
                if str(getattr(e.directness, "value", e.directness)) == "direct":
                    direct += 1
                else:
                    indirect += 1
    open_conflicts = db.execute(select(func.count()).select_from(EvidenceConflict).where(
        EvidenceConflict.organization_id == org, EvidenceConflict.claim_id.in_(claims),
        EvidenceConflict.status.in_(("unreviewed", "under_review", "partially_resolved")))).scalar_one()
    gaps = db.execute(select(func.count()).select_from(KnowledgeGap).where(
        KnowledgeGap.organization_id == org, KnowledgeGap.knowledge_object_id == topic_id)).scalar_one()
    return {"claims": len(claims), "supported_claims": len(supported),
            "unsupported_claims": len(claims) - len(supported),
            "contradicted_claims": len(contradicted), "evidence_rows": len(ev_ids), "verified_evidence": verified,
            "direct": direct, "indirect": indirect, "open_conflicts": int(open_conflicts), "gaps": int(gaps),
            "percent_supported": _pct(len(supported), len(claims)),
            "note": "Indirect evidence is counted separately and never added to the direct figure."}


def _section_dimension(db: Session, org: UUID, topic_id: UUID) -> dict:
    rows = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == org,
        KnowledgeSection.knowledge_object_id == topic_id)).scalars().all()
    if not rows:
        return {"sections": 0, "percent_documented": None,
                "note": "This topic has no section schema applied; section coverage is unknown, not zero."}
    by_status: dict = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    answerable = [r for r in rows if r.status not in CLOSED_SECTION_STATES]
    done = sum(1 for r in rows if r.status in READ_SECTION_STATES)
    return {"sections": len(rows), "by_status": by_status,
            "documented_or_verified": done, "still_open": sum(1 for r in rows if r.status in OPEN_SECTION_STATES),
            "closed_with_a_reason": sum(1 for r in rows if r.status in CLOSED_SECTION_STATES),
            "in_error": by_status.get("error", 0),
            "percent_documented": _pct(done, len(answerable)),
            "note": ("The percentage is of sections that can still be answered; sections closed with a written "
                     "reason are excluded from the denominator rather than counted as failures.")}


def _publication_dimension(db: Session, org: UUID, topic: KnowledgeObject) -> dict:
    """Publication coverage is honest about not existing yet: there is no publication engine in the
    repository, so this reports the KO's own visibility state and says the rest is unavailable."""
    return {"knowledge_version": topic.version, "status": str(getattr(topic.status, "value", topic.status)),
            "public_visibility": topic.public_visibility, "ai_visibility": topic.ai_visibility,
            "published_sections": None, "citation_coverage": None,
            "note": ("No publication or citation layer exists yet (planned as migrations 0035–0036), so these "
                     "figures are unavailable rather than zero.")}


# ---------------------------------------------------------------- running an audit
def _next_version(db: Session, org: UUID, scope: str, topic_id: UUID | None, category_id: UUID | None) -> int:
    return (db.execute(select(func.coalesce(func.max(CoverageAudit.audit_version), 0)).where(
        CoverageAudit.organization_id == org, CoverageAudit.scope == scope,
        CoverageAudit.knowledge_object_id == topic_id,
        CoverageAudit.category_id == category_id)).scalar_one()) + 1


def run_topic_audit(db: Session, *, organization_id: UUID, knowledge_object_id: UUID,
                    trigger: str = "manual") -> CoverageAudit:
    topic = db.execute(select(KnowledgeObject).where(
        KnowledgeObject.id == knowledge_object_id,
        KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if topic is None:
        raise HTTPException(404, "Knowledge object not found.")
    started = _now()
    version = _next_version(db, organization_id, "topic", topic.id, None)
    row = CoverageAudit(organization_id=organization_id, scope="topic", knowledge_object_id=topic.id,
                        audit_version=version, status="running", trigger=trigger, started_at=started,
                        knowledge_version=topic.version)
    db.add(row)
    db.flush()
    try:
        source_ids = list(db.execute(select(Evidence.source_id).where(
            Evidence.organization_id == organization_id,
            Evidence.source_id.isnot(None),
            Evidence.id.in_(select(ClaimEvidence.evidence_id).where(
                ClaimEvidence.claim_id.in_(select(Claim.id).where(
                    Claim.knowledge_object_id == topic.id)))))).scalars().all())
        source_ids = list({s for s in source_ids if s})
        row.dimensions = {
            "source": _source_dimension(db, organization_id, source_ids),
            "processing": _processing_dimension(db, organization_id, source_ids),
            "knowledge": _knowledge_dimension(db, organization_id, topic.id),
            "evidence": _evidence_dimension(db, organization_id, topic.id),
            "section": _section_dimension(db, organization_id, topic.id),
            "publication": _publication_dimension(db, organization_id, topic),
        }
        row.status = "succeeded"
    except Exception as exc:                       # §78 — the failure is its own row; the last good one stands
        row.status = "failed"
        row.failure_reason = f"{type(exc).__name__}: {str(exc)[:400]}"
        row.dimensions = None
    row.finished_at = _now()
    row.duration_ms = int((row.finished_at - started).total_seconds() * 1000)
    db.commit()
    db.refresh(row)
    return row


def run_category_audit(db: Session, *, organization_id: UUID, category_id: UUID,
                       trigger: str = "manual") -> CoverageAudit:
    """§22 — cross-topic analysis, not a sum of topic rows."""
    cat = db.execute(select(Category).where(Category.id == category_id,
                                            Category.organization_id == organization_id)).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Category not found.")
    started = _now()
    version = _next_version(db, organization_id, "category", None, cat.id)
    row = CoverageAudit(organization_id=organization_id, scope="category", category_id=cat.id,
                        audit_version=version, status="running", trigger=trigger, started_at=started,
                        schema_version=cat.schema_version)
    db.add(row)
    db.flush()
    try:
        topics = db.execute(select(KnowledgeObject).where(
            KnowledgeObject.organization_id == organization_id,
            KnowledgeObject.category_id == cat.id)).scalars().all()
        topic_ids = [t.id for t in topics]
        defs = db.execute(select(SectionDefinition).where(
            SectionDefinition.organization_id == organization_id,
            SectionDefinition.category_id == cat.id)).scalars().all()
        cells = db.execute(select(KnowledgeSection).where(
            KnowledgeSection.organization_id == organization_id,
            KnowledgeSection.knowledge_object_id.in_(topic_ids))).scalars().all() if topic_ids else []
        latest = {t.id: latest_audit(db, organization_id=organization_id, scope="topic", knowledge_object_id=t.id)
                  for t in topics}
        stale = [str(t.id) for t in topics
                 if latest[t.id] is None or (latest[t.id].knowledge_version or -1) != t.version]
        # which sections are weak ACROSS the category — the thing a per-topic view cannot show
        per_section: dict = {}
        for d in defs:
            mine = [c for c in cells if c.section_key == d.key]
            documented = sum(1 for c in mine if c.status in READ_SECTION_STATES)
            per_section[d.key] = {"title": d.title, "topics_with_the_cell": len(mine),
                                  "topics_in_category": len(topics),
                                  "documented_or_verified": documented,
                                  "missing_entirely": len(topics) - len(mine),
                                  "percent_documented": _pct(documented, len(topics))}
        pending = db.execute(select(func.count()).select_from(SectionPropagation).where(
            SectionPropagation.organization_id == organization_id,
            SectionPropagation.state == "pending",
            SectionPropagation.section_definition_id.in_([d.id for d in defs]))).scalar_one() if defs else 0
        weakest = sorted((v for v in per_section.values() if v["percent_documented"] is not None),
                         key=lambda v: v["percent_documented"])[:5]
        row.dimensions = {"topics": len(topics), "sections_in_schema": len(defs),
                          "cells_present": len(cells), "cells_expected": len(topics) * len(defs)}
        row.cross_topic = {"per_section": per_section, "weakest_sections": weakest,
                           "stale_topics": stale, "pending_cross_topic_evaluations": int(pending),
                           "note": ("Computed across the category. A section may be documented on one topic and "
                                    "missing on every other — a sum of topic figures would hide that.")}
        row.status = "succeeded"
    except Exception as exc:
        row.status = "failed"
        row.failure_reason = f"{type(exc).__name__}: {str(exc)[:400]}"
    row.finished_at = _now()
    row.duration_ms = int((row.finished_at - started).total_seconds() * 1000)
    db.commit()
    db.refresh(row)
    return row


def latest_audit(db: Session, *, organization_id: UUID, scope: str, knowledge_object_id: UUID | None = None,
                 category_id: UUID | None = None, succeeded_only: bool = True) -> CoverageAudit | None:
    stmt = select(CoverageAudit).where(CoverageAudit.organization_id == organization_id,
                                       CoverageAudit.scope == scope,
                                       CoverageAudit.knowledge_object_id == knowledge_object_id,
                                       CoverageAudit.category_id == category_id)
    if succeeded_only:
        stmt = stmt.where(CoverageAudit.status == "succeeded")
    return db.execute(stmt.order_by(CoverageAudit.audit_version.desc()).limit(1)).scalar_one_or_none()


def audit_out(a: CoverageAudit) -> dict:
    return {"id": str(a.id), "scope": a.scope, "audit_version": a.audit_version, "status": a.status,
            "failure_reason": a.failure_reason, "knowledge_object_id": str(a.knowledge_object_id) if a.knowledge_object_id else None,
            "category_id": str(a.category_id) if a.category_id else None,
            "knowledge_version": a.knowledge_version, "schema_version": a.schema_version, "trigger": a.trigger,
            "started_at": a.started_at, "finished_at": a.finished_at, "duration_ms": a.duration_ms,
            "dimensions": a.dimensions, "cross_topic": a.cross_topic}


def current_view(db: Session, *, organization_id: UUID, scope: str, knowledge_object_id: UUID | None = None,
                 category_id: UUID | None = None) -> dict:
    """What the Dashboard reads. If the newest attempt failed, the last good audit is returned and
    explicitly marked stale — never replaced by an empty one (§78)."""
    good = latest_audit(db, organization_id=organization_id, scope=scope,
                        knowledge_object_id=knowledge_object_id, category_id=category_id)
    newest = latest_audit(db, organization_id=organization_id, scope=scope,
                          knowledge_object_id=knowledge_object_id, category_id=category_id, succeeded_only=False)
    if good is None and newest is None:
        return {"state": "never_run", "audit": None,
                "message": "No coverage audit has run for this scope yet."}
    if newest is not None and newest.status == "failed" and (good is None or newest.audit_version > good.audit_version):
        return {"state": "stale", "audit": audit_out(good) if good else None,
                "failed_attempt": {"audit_version": newest.audit_version, "reason": newest.failure_reason,
                                   "at": newest.finished_at},
                "message": ("The last audit failed. The figures below are the last successful audit, not current."
                            if good else "The only audit attempt failed; there are no figures to show.")}
    return {"state": "current", "audit": audit_out(good), "message": None}
