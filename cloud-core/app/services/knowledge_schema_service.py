"""
Category schema, sections and the Master Topic Matrix (ADR-114).

Three rules shape everything here:

1. A cell's status is derived from what the knowledge base actually holds — claims, evidence, conflicts,
   gaps — never asserted by hand except for the two states that mean "stop looking", and those require a
   written reason (the database enforces it).
2. A section discovered on one topic is *proposed* for its siblings, never copied into them. Nothing is
   written into a sibling's knowledge until a person or a research run decides.
3. A failed recalculation preserves the last good status (§78). Nothing is ever replaced by zero.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence import Evidence
from app.models.evidence_conflict import EvidenceConflict
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_object import KnowledgeObject
from app.models.knowledge_schema import (
    SECTION_STATUSES, Category, KnowledgeSection, SectionDefinition, SectionPropagation,
)

# A starting schema per category kind. These are proposals the owner edits — not a fixed template (§11).
STARTER_SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "medicinal_plant": [
        ("identity", "Identity"), ("names", "Names and synonyms"), ("multilingual_names", "Names by language"),
        ("taxonomy", "Taxonomy"), ("morphology", "Morphology"), ("distribution", "Geographical distribution"),
        ("traditional_uses", "Traditional uses"), ("composition", "Chemical composition"),
        ("pharmacology", "Pharmacology"), ("therapeutic_properties", "Therapeutic properties"),
        ("clinical_evidence", "Clinical evidence"), ("safety", "Safety"), ("dosage", "Dosage"),
        ("preparation", "Preparation"), ("interactions", "Interactions"),
        ("contraindications", "Contraindications"), ("authenticity", "Authenticity"),
        ("adulteration", "Adulteration"),
    ],
    "device": [
        ("identity", "Identity"), ("models", "Models"), ("hardware", "Hardware"), ("display", "Display"),
        ("processor", "Processor"), ("camera", "Camera"), ("battery", "Battery"), ("software", "Software"),
        ("security", "Security"), ("connectivity", "Connectivity"), ("compatibility", "Compatibility"),
        ("pricing", "Pricing"), ("availability", "Availability"), ("testing", "Independent testing"),
        ("known_issues", "Known issues"), ("comparisons", "Comparisons"),
    ],
    "generic": [
        ("identity", "Identity"), ("names", "Names"), ("description", "Description"),
        ("composition", "Composition or components"), ("uses", "Uses"), ("evidence", "Evidence"),
        ("safety", "Safety"), ("sources", "Sources"),
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    s = re.sub(r"[^\w\s-]", "", value.strip().lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:200] or "category"


# ---------------------------------------------------------------- categories
def create_category(db: Session, *, organization_id: UUID, name: str, description: str | None,
                    starter: str | None, parent_category_id: UUID | None) -> Category:
    slug = slugify(name)
    if db.execute(select(Category).where(Category.organization_id == organization_id,
                                         Category.slug == slug)).scalar_one_or_none():
        raise HTTPException(409, "A category with that name already exists.")
    if parent_category_id and _category(db, organization_id, parent_category_id) is None:
        raise HTTPException(404, "Parent category not found.")
    cat = Category(organization_id=organization_id, name=name.strip(), slug=slug, description=description,
                   parent_category_id=parent_category_id, schema_version=1)
    db.add(cat)
    db.flush()
    if starter:
        if starter not in STARTER_SCHEMAS:
            raise HTTPException(422, f"starter must be one of: {', '.join(STARTER_SCHEMAS)}")
        for i, (key, title) in enumerate(STARTER_SCHEMAS[starter]):
            db.add(SectionDefinition(organization_id=organization_id, category_id=cat.id, key=key, title=title,
                                     position=i, required=True, origin="category_schema", schema_version=1))
    db.commit()
    db.refresh(cat)
    return cat


def _category(db: Session, organization_id: UUID, category_id: UUID) -> Category | None:
    return db.execute(select(Category).where(Category.id == category_id,
                                             Category.organization_id == organization_id)).scalar_one_or_none()


def category_or_404(db: Session, organization_id: UUID, category_id: UUID) -> Category:
    cat = _category(db, organization_id, category_id)
    if cat is None:
        raise HTTPException(404, "Category not found.")
    return cat


def category_out(c: Category) -> dict:
    return {"id": str(c.id), "name": c.name, "slug": c.slug, "description": c.description,
            "schema_version": c.schema_version,
            "parent_category_id": str(c.parent_category_id) if c.parent_category_id else None,
            "created_at": c.created_at}


# ---------------------------------------------------------------- section definitions
def add_section_definition(db: Session, *, organization_id: UUID, category_id: UUID, key: str, title: str,
                           description: str | None, required: bool, origin: str = "user_added",
                           discovered_from_topic_id: UUID | None = None,
                           discovered_evidence_id: UUID | None = None) -> SectionDefinition:
    cat = category_or_404(db, organization_id, category_id)
    key = slugify(key).replace("-", "_")
    if db.execute(select(SectionDefinition).where(SectionDefinition.organization_id == organization_id,
                                                  SectionDefinition.category_id == category_id,
                                                  SectionDefinition.key == key)).scalar_one_or_none():
        raise HTTPException(409, "That section already exists in this category.")
    nxt = db.execute(select(func.coalesce(func.max(SectionDefinition.position), -1) + 1)
                     .where(SectionDefinition.category_id == category_id)).scalar_one()
    sd = SectionDefinition(organization_id=organization_id, category_id=category_id, key=key, title=title.strip(),
                           description=description, position=nxt, required=required, origin=origin,
                           discovered_from_topic_id=discovered_from_topic_id,
                           discovered_evidence_id=discovered_evidence_id, schema_version=cat.schema_version + 1)
    cat.schema_version += 1           # the schema moved: a recomputed matrix stays auditable against it
    db.add(sd)
    db.flush()
    _propose_to_siblings(db, organization_id=organization_id, definition=sd)
    db.commit()
    db.refresh(sd)
    return sd


def definition_out(d: SectionDefinition) -> dict:
    return {"id": str(d.id), "category_id": str(d.category_id), "key": d.key, "title": d.title,
            "description": d.description, "position": d.position, "required": d.required, "origin": d.origin,
            "discovered_from_topic_id": str(d.discovered_from_topic_id) if d.discovered_from_topic_id else None,
            "reviewed_at": d.reviewed_at, "schema_version": d.schema_version}


def _topics(db: Session, organization_id: UUID, category_id: UUID) -> list[KnowledgeObject]:
    return list(db.execute(select(KnowledgeObject).where(
        KnowledgeObject.organization_id == organization_id,
        KnowledgeObject.category_id == category_id).order_by(KnowledgeObject.canonical_name)).scalars().all())


def _propose_to_siblings(db: Session, *, organization_id: UUID, definition: SectionDefinition) -> int:
    """§16 — every sibling topic gets a PENDING proposal. Nothing is written into their knowledge."""
    made = 0
    for topic in _topics(db, organization_id, definition.category_id):
        if topic.id == definition.discovered_from_topic_id:
            continue
        exists = db.execute(select(SectionPropagation).where(
            SectionPropagation.organization_id == organization_id,
            SectionPropagation.section_definition_id == definition.id,
            SectionPropagation.knowledge_object_id == topic.id)).scalar_one_or_none()
        if exists:
            continue
        db.add(SectionPropagation(organization_id=organization_id, section_definition_id=definition.id,
                                  knowledge_object_id=topic.id, state="pending"))
        made += 1
    return made


def decide_propagation(db: Session, *, organization_id: UUID, propagation_id: UUID, state: str,
                       resulting_status: str | None, note: str | None, actor_user_id: UUID) -> dict:
    if state not in ("evaluated", "skipped"):
        raise HTTPException(422, "state must be evaluated or skipped")
    row = db.execute(select(SectionPropagation).where(
        SectionPropagation.id == propagation_id,
        SectionPropagation.organization_id == organization_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Proposal not found.")
    if state == "skipped" and not (note or "").strip():
        raise HTTPException(422, "Say why this section does not apply here.")
    if state == "evaluated":
        if resulting_status not in SECTION_STATUSES:
            raise HTTPException(422, f"resulting_status must be one of: {', '.join(SECTION_STATUSES)}")
        if resulting_status in ("not_applicable", "no_evidence_found") and not (note or "").strip():
            raise HTTPException(422, "Closing a section needs a written reason.")
        definition = db.get(SectionDefinition, row.section_definition_id)
        _ensure_section(db, organization_id=organization_id, topic_id=row.knowledge_object_id,
                        definition=definition, status=resulting_status, rationale=(note or None),
                        origin="discovered")
    row.state = state
    row.resulting_status = resulting_status if state == "evaluated" else None
    row.note = (note or "").strip() or None
    row.decided_by_user_id = actor_user_id
    row.decided_at = _now()
    db.commit()
    db.refresh(row)
    return propagation_out(row)


def propagation_out(p: SectionPropagation) -> dict:
    return {"id": str(p.id), "section_definition_id": str(p.section_definition_id),
            "knowledge_object_id": str(p.knowledge_object_id), "state": p.state,
            "resulting_status": p.resulting_status, "note": p.note, "decided_at": p.decided_at,
            "created_at": p.created_at}


# ---------------------------------------------------------------- cells
def _ensure_section(db: Session, *, organization_id: UUID, topic_id: UUID, definition: SectionDefinition | None,
                    status: str = "needs_research", rationale: str | None = None,
                    origin: str = "category_schema", section_key: str | None = None,
                    title: str | None = None) -> KnowledgeSection:
    key = section_key or (definition.key if definition else None)
    if key is None:
        raise HTTPException(422, "A section needs a key.")
    row = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id,
        KnowledgeSection.knowledge_object_id == topic_id,
        KnowledgeSection.section_key == key)).scalar_one_or_none()
    if row is None:
        row = KnowledgeSection(organization_id=organization_id, knowledge_object_id=topic_id,
                               section_definition_id=definition.id if definition else None, section_key=key,
                               title=title or (definition.title if definition else key.replace("_", " ").title()),
                               status=status, rationale=rationale, origin=origin)
        db.add(row)
        db.flush()
    return row


def apply_schema(db: Session, *, organization_id: UUID, knowledge_object_id: UUID) -> dict:
    """Give a topic one cell per section its category expects. Existing cells are never overwritten."""
    topic = db.execute(select(KnowledgeObject).where(
        KnowledgeObject.id == knowledge_object_id,
        KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if topic is None:
        raise HTTPException(404, "Knowledge object not found.")
    if topic.category_id is None:
        raise HTTPException(409, "This topic has no category, so there is no schema to apply.")
    defs = db.execute(select(SectionDefinition).where(
        SectionDefinition.organization_id == organization_id,
        SectionDefinition.category_id == topic.category_id).order_by(SectionDefinition.position)).scalars().all()
    before = db.execute(select(func.count()).select_from(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id,
        KnowledgeSection.knowledge_object_id == topic.id)).scalar_one()
    for d in defs:
        _ensure_section(db, organization_id=organization_id, topic_id=topic.id, definition=d)
    db.commit()
    after = db.execute(select(func.count()).select_from(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id,
        KnowledgeSection.knowledge_object_id == topic.id)).scalar_one()
    return {"knowledge_object_id": str(topic.id), "sections_in_schema": len(defs),
            "created": after - before, "total": after}


# ---------------------------------------------------------------- recalculation (§17, §23, §78)
MANUAL_STATUSES = ("not_applicable", "field_research", "experiment_required", "user_input", "outdated")


def _section_counts(db: Session, *, organization_id: UUID, topic_id: UUID, section_key: str) -> dict:
    """What the knowledge base actually holds for this cell.

    A claim belongs to a section through `claims.section_key`; evidence is counted through the claim it
    supports, so a cell can never inherit evidence that was never linked to its claims."""
    claims = db.execute(select(Claim).where(Claim.organization_id == organization_id,
                                            Claim.knowledge_object_id == topic_id)).scalars().all()
    mine = [c for c in claims if c.section_key == section_key]
    ids = [c.id for c in mine]
    evidence_ids: set = set()
    direct = 0
    if ids:
        links = db.execute(select(ClaimEvidence).where(ClaimEvidence.organization_id == organization_id,
                                                       ClaimEvidence.claim_id.in_(ids))).scalars().all()
        evidence_ids = {l.evidence_id for l in links}
        if evidence_ids:
            rows = db.execute(select(Evidence).where(Evidence.id.in_(evidence_ids))).scalars().all()
            direct = sum(1 for e in rows
                         if str(getattr(e.directness, "value", e.directness)) == "direct"
                         and str(getattr(e.status, "value", e.status)) == "verified")
    conflicts = db.execute(select(func.count()).select_from(EvidenceConflict).where(
        EvidenceConflict.organization_id == organization_id,
        EvidenceConflict.claim_id.in_(ids) if ids else False,
        EvidenceConflict.status.in_(("unreviewed", "under_review", "partially_resolved")))).scalar_one() if ids else 0
    gaps = db.execute(select(func.count()).select_from(KnowledgeGap).where(
        KnowledgeGap.organization_id == organization_id,
        KnowledgeGap.knowledge_object_id == topic_id)).scalar_one()
    approved = sum(1 for c in mine if str(getattr(c.status, "value", c.status)) == "approved")
    reviewed = sum(1 for c in mine if c.human_reviewed)
    return {"claims": len(mine), "approved": approved, "reviewed": reviewed, "evidence": len(evidence_ids),
            "direct": direct, "conflicts": int(conflicts), "gaps": int(gaps)}


def _derive_status(counts: dict, current: str) -> str:
    """The rules, in order. A cell a person has closed or escalated is never re-opened automatically."""
    if current in MANUAL_STATUSES:
        return current
    if counts["conflicts"]:
        return "conflicting"
    if counts["claims"] == 0:
        return "needs_research" if current in ("needs_research", "processing", "new", "error") else current
    if counts["evidence"] == 0:
        return "partial"
    if counts["approved"] == counts["claims"] and counts["reviewed"] == counts["claims"]:
        return "verified"
    if counts["approved"]:
        return "documented"
    return "partial"


def recalculate_section(db: Session, *, organization_id: UUID, section: KnowledgeSection,
                        commit: bool = True) -> KnowledgeSection:
    try:
        counts = _section_counts(db, organization_id=organization_id,
                                 topic_id=section.knowledge_object_id, section_key=section.section_key)
    except Exception as exc:                      # §78 — keep the last good state, never fall back to zero
        if section.status != "error":
            section.last_good_status = section.status
        section.status = "error"
        section.rationale = f"recalculation failed: {type(exc).__name__}"
        section.last_audited_at = _now()
        if commit:
            db.commit()
        return section
    section.claim_count = counts["claims"]
    section.evidence_count = counts["evidence"]
    section.direct_evidence_count = counts["direct"]
    section.conflict_count = counts["conflicts"]
    section.gap_count = counts["gaps"]
    section.status = _derive_status(counts, section.status)
    section.last_good_status = section.status
    section.last_audited_at = _now()
    if commit:
        db.commit()
    return section


def recalculate_topic(db: Session, *, organization_id: UUID, knowledge_object_id: UUID) -> dict:
    rows = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id,
        KnowledgeSection.knowledge_object_id == knowledge_object_id)).scalars().all()
    for r in rows:
        recalculate_section(db, organization_id=organization_id, section=r, commit=False)
    db.commit()
    return {"knowledge_object_id": str(knowledge_object_id), "sections": len(rows),
            "by_status": _tally(rows), "audited_at": _now()}


def _tally(rows) -> dict:  # noqa: ANN001
    out: dict = {}
    for r in rows:
        out[r.status] = out.get(r.status, 0) + 1
    return out


def section_out(s: KnowledgeSection) -> dict:
    return {"id": str(s.id), "knowledge_object_id": str(s.knowledge_object_id), "section_key": s.section_key,
            "title": s.title, "status": s.status, "last_good_status": s.last_good_status,
            "rationale": s.rationale, "origin": s.origin, "claims": s.claim_count, "evidence": s.evidence_count,
            "direct_evidence": s.direct_evidence_count, "conflicts": s.conflict_count, "gaps": s.gap_count,
            "research_question_id": str(s.research_question_id) if s.research_question_id else None,
            "last_research_at": s.last_research_at, "last_audited_at": s.last_audited_at}


def set_section_status(db: Session, *, organization_id: UUID, section_id: UUID, status: str,
                       rationale: str | None) -> dict:
    """A person closes or escalates a cell. The two closing states require a reason — so does the database."""
    if status not in SECTION_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(SECTION_STATUSES)}")
    if status == "error":
        raise HTTPException(422, "'error' is set by the system, not by hand.")
    row = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.id == section_id, KnowledgeSection.organization_id == organization_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Section not found.")
    if status in ("not_applicable", "no_evidence_found") and not (rationale or "").strip():
        raise HTTPException(422, "Closing a section needs a written reason.")
    row.status = status
    row.last_good_status = status
    if rationale is not None:
        row.rationale = rationale.strip() or None
    row.last_audited_at = _now()
    db.commit()
    db.refresh(row)
    return section_out(row)


# ---------------------------------------------------------------- the Master Topic Matrix (§13)
def matrix(db: Session, *, organization_id: UUID, category_id: UUID) -> dict:
    """Rows are sections, columns are topics, and every cell is live data — never a static table."""
    cat = category_or_404(db, organization_id, category_id)
    topics = _topics(db, organization_id, category_id)
    defs = db.execute(select(SectionDefinition).where(
        SectionDefinition.organization_id == organization_id,
        SectionDefinition.category_id == category_id).order_by(SectionDefinition.position)).scalars().all()
    topic_ids = [t.id for t in topics]
    cells = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == organization_id,
        KnowledgeSection.knowledge_object_id.in_(topic_ids))).scalars().all() if topic_ids else []
    by = {(c.knowledge_object_id, c.section_key): c for c in cells}
    # a section a topic has but the schema does not: keep it visible rather than hiding it
    extra = sorted({c.section_key for c in cells} - {d.key for d in defs})
    rows = []
    for d in defs:
        rows.append({"section_key": d.key, "title": d.title, "required": d.required, "origin": d.origin,
                     "cells": [_cell(by.get((t.id, d.key)), t) for t in topics]})
    for key in extra:
        sample = next(c for c in cells if c.section_key == key)
        rows.append({"section_key": key, "title": sample.title, "required": False, "origin": sample.origin,
                     "in_schema": False, "cells": [_cell(by.get((t.id, key)), t) for t in topics]})
    pending = db.execute(select(func.count()).select_from(SectionPropagation).where(
        SectionPropagation.organization_id == organization_id,
        SectionPropagation.state == "pending",
        SectionPropagation.section_definition_id.in_([d.id for d in defs]) if defs else False)).scalar_one() if defs else 0
    return {"category": category_out(cat),
            "topics": [{"id": str(t.id), "name": t.canonical_name, "object_type": t.object_type} for t in topics],
            "sections": len(defs), "rows": rows, "sections_outside_schema": extra,
            "pending_cross_topic_evaluations": int(pending),
            "note": ("Every cell is read from the knowledge base. An empty cell means the section has never been "
                     "researched for that topic — not that the section does not apply.")}


def _cell(section: KnowledgeSection | None, topic: KnowledgeObject) -> dict:
    if section is None:
        return {"knowledge_object_id": str(topic.id), "status": None, "exists": False,
                "label": "not yet in this topic"}
    return {"knowledge_object_id": str(topic.id), "section_id": str(section.id), "exists": True,
            "status": section.status, "label": section.status.replace("_", " "),
            "claims": section.claim_count, "evidence": section.evidence_count,
            "direct_evidence": section.direct_evidence_count, "conflicts": section.conflict_count,
            "rationale": section.rationale, "last_audited_at": section.last_audited_at}
