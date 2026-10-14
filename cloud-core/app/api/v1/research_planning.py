"""Research query sets (§12) and evidence-completion tasks (§16)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.research_planning import EvidenceCompletionTask, ResearchQuerySet
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import research_planning_service as svc

router = APIRouter(tags=["research-planning"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
Reader = Depends(get_current_user)


class QuerySetIn(BaseModel):
    knowledge_object_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    keyword_ids: list[UUID] = Field(default_factory=list, max_length=50)
    extra_terms: list[str] = Field(default_factory=list, max_length=30)
    mode: Literal["single", "multi", "exact", "boolean", "agent"] = "agent"
    boolean_query: str | None = Field(default=None, max_length=1000)


class QuerySetPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    keyword_ids: list[UUID] | None = None
    extra_terms: list[str] | None = None
    mode: Literal["single", "multi", "exact", "boolean", "agent"] | None = None
    boolean_query: str | None = None


class CompletionIn(BaseModel):
    knowledge_object_id: UUID
    what_is_missing: str = Field(min_length=3, max_length=2000)
    claim_id: UUID | None = None
    knowledge_gap_id: UUID | None = None
    research_question_id: UUID | None = None
    required_route: str | None = None
    required_directness: Literal["direct", "indirect"] | None = None


class CompletionPatch(BaseModel):
    status: Literal["open", "searching", "awaiting_review", "satisfied", "blocked", "abandoned"]
    satisfied_by_evidence_id: UUID | None = None
    outcome_note: str | None = Field(default=None, max_length=2000)


@router.get("/research/query-sets", response_model=Page[dict])
def list_sets(p: PaginationParams = Depends(), sort: SortParams = Depends(), knowledge_object_id: UUID | None = None,
              user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(ResearchQuerySet).where(ResearchQuerySet.organization_id == user.organization_id)
    if knowledge_object_id:
        stmt = stmt.where(ResearchQuerySet.knowledge_object_id == knowledge_object_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, ResearchQuerySet, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.set_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/research/query-sets", status_code=201)
def create_set(body: QuerySetIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.create_set(db, organization_id=user.organization_id, **body.model_dump())


@router.patch("/research/query-sets/{set_id}")
def update_set(set_id: UUID, body: QuerySetPatch, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.update_set(db, organization_id=user.organization_id, set_id=set_id, patch=body.model_dump(exclude_unset=True))


@router.post("/research/query-sets/{set_id}/run", status_code=201)
def run_set(set_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.run_set(db, organization_id=user.organization_id, set_id=set_id, actor=user.id)


@router.get("/evidence-completion-tasks", response_model=Page[dict])
def list_tasks(p: PaginationParams = Depends(), sort: SortParams = Depends(), status: str | None = None,
               knowledge_object_id: UUID | None = None, user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(EvidenceCompletionTask).where(EvidenceCompletionTask.organization_id == user.organization_id)
    if status:
        stmt = stmt.where(EvidenceCompletionTask.status == status)
    if knowledge_object_id:
        stmt = stmt.where(EvidenceCompletionTask.knowledge_object_id == knowledge_object_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, EvidenceCompletionTask, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.task_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/evidence-completion-tasks", status_code=201)
def create_task(body: CompletionIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.create_task(db, organization_id=user.organization_id, **body.model_dump())


@router.patch("/evidence-completion-tasks/{task_id}")
def update_task(task_id: UUID, body: CompletionPatch, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.update_task(db, organization_id=user.organization_id, task_id=task_id, status=body.status,
                           satisfied_by_evidence_id=body.satisfied_by_evidence_id, outcome_note=body.outcome_note,
                           actor_user_id=user.id)
