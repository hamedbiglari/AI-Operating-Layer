"""
Research query sets (§12) and evidence-completion tasks (§16) — ADR-111.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_center import KnowledgeKeyword
from app.models.evidence import Evidence
from app.models.knowledge_object import KnowledgeObject
from app.models.research_planning import COMPLETION_STATES, EvidenceCompletionTask, ResearchQuerySet


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ko(db: Session, organization_id: UUID, ko_id: UUID) -> KnowledgeObject:
    ko = db.execute(select(KnowledgeObject).where(KnowledgeObject.id == ko_id,
                                                  KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if ko is None:
        raise HTTPException(404, "Knowledge object not found.")
    return ko


def set_out(s: ResearchQuerySet) -> dict:
    return {"id": str(s.id), "knowledge_object_id": str(s.knowledge_object_id), "name": s.name,
            "description": s.description, "keyword_ids": s.keyword_ids or [], "extra_terms": s.extra_terms or [],
            "mode": s.mode, "boolean_query": s.boolean_query, "run_count": s.run_count,
            "last_run_at": s.last_run_at, "created_at": s.created_at}


def create_set(db: Session, *, organization_id: UUID, knowledge_object_id: UUID, name: str, description: str | None,
               keyword_ids: list[UUID], extra_terms: list[str], mode: str, boolean_query: str | None) -> dict:
    _ko(db, organization_id, knowledge_object_id)
    if keyword_ids:
        found = db.execute(select(func.count()).select_from(KnowledgeKeyword).where(
            KnowledgeKeyword.organization_id == organization_id,
            KnowledgeKeyword.knowledge_object_id == knowledge_object_id,
            KnowledgeKeyword.id.in_(keyword_ids))).scalar_one()
        if found != len(set(keyword_ids)):
            raise HTTPException(404, "Keyword not found for this knowledge object.")
    if db.execute(select(ResearchQuerySet).where(ResearchQuerySet.organization_id == organization_id,
                                                 ResearchQuerySet.knowledge_object_id == knowledge_object_id,
                                                 ResearchQuerySet.name == name)).scalar_one_or_none():
        raise HTTPException(409, "A query set with that name already exists for this knowledge object.")
    row = ResearchQuerySet(organization_id=organization_id, knowledge_object_id=knowledge_object_id, name=name.strip(),
                           description=description, keyword_ids=[str(k) for k in keyword_ids] or None,
                           extra_terms=extra_terms or None, mode=mode, boolean_query=boolean_query)
    db.add(row)
    db.commit()
    db.refresh(row)
    return set_out(row)


def get_set(db: Session, organization_id: UUID, set_id: UUID) -> ResearchQuerySet:
    row = db.execute(select(ResearchQuerySet).where(ResearchQuerySet.id == set_id,
                                                    ResearchQuerySet.organization_id == organization_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Query set not found.")
    return row


def update_set(db: Session, *, organization_id: UUID, set_id: UUID, patch: dict) -> dict:
    row = get_set(db, organization_id, set_id)
    for k in ("name", "description", "extra_terms", "mode", "boolean_query"):
        if k in patch and patch[k] is not None:
            setattr(row, k, patch[k])
    if patch.get("keyword_ids") is not None:
        row.keyword_ids = [str(k) for k in patch["keyword_ids"]] or None
    db.commit()
    db.refresh(row)
    return set_out(row)


def run_set(db: Session, *, organization_id: UUID, set_id: UUID, actor: UUID, providers: list | None = None) -> dict:
    """Run a saved set exactly as it is written, and count the run so it can be compared over time."""
    from app.services import federated_research_service as fsvc

    row = get_set(db, organization_id, set_id)
    result = fsvc.keyword_search(db, organization_id=organization_id, actor=actor,
                                 knowledge_object_id=row.knowledge_object_id,
                                 keyword_ids=[UUID(k) for k in (row.keyword_ids or [])], mode=row.mode,
                                 boolean_query=row.boolean_query, providers=providers)
    row.run_count += 1
    row.last_run_at = _now()
    db.commit()
    return {"query_set": set_out(row), "run": result}


# ---------------------------------------------------------------- evidence completion (§16)
def task_out(t: EvidenceCompletionTask) -> dict:
    return {"id": str(t.id), "knowledge_object_id": str(t.knowledge_object_id),
            "claim_id": str(t.claim_id) if t.claim_id else None,
            "knowledge_gap_id": str(t.knowledge_gap_id) if t.knowledge_gap_id else None,
            "research_question_id": str(t.research_question_id) if t.research_question_id else None,
            "what_is_missing": t.what_is_missing, "required_route": t.required_route,
            "required_directness": t.required_directness, "status": t.status,
            "satisfied_by_evidence_id": str(t.satisfied_by_evidence_id) if t.satisfied_by_evidence_id else None,
            "outcome_note": t.outcome_note, "closed_at": t.closed_at, "created_at": t.created_at}


def create_task(db: Session, *, organization_id: UUID, knowledge_object_id: UUID, what_is_missing: str,
                claim_id: UUID | None, knowledge_gap_id: UUID | None, research_question_id: UUID | None,
                required_route: str | None, required_directness: str | None) -> dict:
    from app.models.research_federation import EVIDENCE_ROUTES

    _ko(db, organization_id, knowledge_object_id)
    if required_route and required_route not in EVIDENCE_ROUTES:
        raise HTTPException(422, f"required_route must be one of: {', '.join(EVIDENCE_ROUTES)}")
    if required_directness and required_directness not in ("direct", "indirect"):
        raise HTTPException(422, "required_directness must be direct or indirect")
    row = EvidenceCompletionTask(organization_id=organization_id, knowledge_object_id=knowledge_object_id,
                                 what_is_missing=what_is_missing.strip(), claim_id=claim_id,
                                 knowledge_gap_id=knowledge_gap_id, research_question_id=research_question_id,
                                 required_route=required_route, required_directness=required_directness, status="open")
    db.add(row)
    db.commit()
    db.refresh(row)
    return task_out(row)


def update_task(db: Session, *, organization_id: UUID, task_id: UUID, status: str,
                satisfied_by_evidence_id: UUID | None, outcome_note: str | None, actor_user_id: UUID) -> dict:
    from app.services.audit import record_audit_log

    if status not in COMPLETION_STATES:
        raise HTTPException(422, f"status must be one of: {', '.join(COMPLETION_STATES)}")
    row = db.execute(select(EvidenceCompletionTask).where(
        EvidenceCompletionTask.id == task_id, EvidenceCompletionTask.organization_id == organization_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Completion task not found.")
    if status == "satisfied":
        if satisfied_by_evidence_id is None:
            raise HTTPException(422, "Name the evidence that satisfies this — a task cannot be satisfied by nothing.")
        ev = db.execute(select(Evidence).where(Evidence.id == satisfied_by_evidence_id,
                                               Evidence.organization_id == organization_id)).scalar_one_or_none()
        if ev is None:
            raise HTTPException(404, "Evidence not found.")
        if str(getattr(ev.status, "value", ev.status)) != "verified":
            raise HTTPException(409, "Only reviewed evidence can satisfy a completion task.")
        if row.required_directness and ev.directness.value != row.required_directness:
            raise HTTPException(409, f"This task requires {row.required_directness} evidence; that finding is {ev.directness.value}.")
        if row.required_route and ev.evidence_route != row.required_route:
            raise HTTPException(409, f"This task requires evidence on the {row.required_route.replace('_', ' ')} route.")
        row.satisfied_by_evidence_id = ev.id
    if status in ("blocked", "abandoned") and not (outcome_note or "").strip():
        raise HTTPException(422, "Say why — a dead end needs a written reason.")
    row.status = status
    if outcome_note is not None:
        row.outcome_note = outcome_note.strip() or None
    row.closed_at = _now() if status in ("satisfied", "blocked", "abandoned") else None
    record_audit_log(db, organization_id=organization_id, user_id=actor_user_id, action="evidence_completion.updated",
                     resource_type="evidence_completion_task", resource_id=row.id, new_value={"status": status})
    db.commit()
    db.refresh(row)
    return task_out(row)
