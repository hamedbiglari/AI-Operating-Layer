"""
Synthesis API (prompt v4.0 §14–§23, §58; ADR-124).

    POST /synthesis/plan                  how the scope would be packed, and whether the budgets allow it
    POST /synthesis/runs                  create and start a run (202); blocked runs say which budget
    GET  /synthesis/runs                  history (filter by topic / status)
    GET  /synthesis/runs/{id}             the run, its coverage counts and its audit
    GET  /synthesis/runs/{id}/units       the per-unit ledger (filter by status: omitted, pending, …)
    POST /synthesis/runs/{id}/resume      continue after a provider stop — completed work is not redone
    POST /synthesis/runs/{id}/cancel
    POST /synthesis/runs/{id}/publish     sentences → claims → sources → Vancouver numbers
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.context_assembly import Budgets
from app.db.session import get_db
from app.models.ai_center import AIJob
from app.models.enums import ADMIN_ROLES, KNOWLEDGE_EDITOR_ROLES
from app.models.synthesis import SynthesisRun, SynthesisUnit
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import ai_job_service, synthesis_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/synthesis", tags=["synthesis"])
Reader = Depends(get_current_user)
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))


class BudgetsIn(BaseModel):
    context_tokens: int = Field(default=24000, ge=1000, le=2_000_000)
    max_output_tokens: int = Field(default=2000, ge=100, le=64000)
    max_calls: int | None = Field(default=None, ge=1)
    max_cost: float | None = Field(default=None, ge=0)


class RunRequest(BaseModel):
    knowledge_object_id: UUID
    task: str = Field(min_length=3, max_length=4000)
    section_key: str | None = None
    claim_ids: list[UUID] | None = None
    directness: str | None = Field(default=None, pattern="^(direct|indirect)$")
    terms: list[str] | None = None
    policy_id: UUID | None = None
    budgets: BudgetsIn = BudgetsIn()
    allow_partial: bool = False


def _get(db: Session, org: UUID, run_id: UUID) -> SynthesisRun:
    run = db.execute(select(SynthesisRun).where(SynthesisRun.id == run_id,
                                                SynthesisRun.organization_id == org)).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Synthesis run not found.")
    return run


def dispatch(run: SynthesisRun) -> None:
    from app.workers.tasks import advance_synthesis_run

    try:
        advance_synthesis_run.delay(str(run.id))
    except Exception as exc:  # broker down: the run stays queued and can be resumed
        logger.warning("synthesis dispatch failed for %s: %s", run.id, exc)


def _start(db: Session, user: User, body: RunRequest, *, plan_only: bool) -> SynthesisRun:
    return svc.create_run(db, organization_id=user.organization_id, user_id=user.id,
                          knowledge_object_id=body.knowledge_object_id, task=body.task,
                          budgets=Budgets(**body.budgets.model_dump()), policy_id=body.policy_id,
                          section_key=body.section_key, claim_ids=body.claim_ids, directness=body.directness,
                          terms=body.terms, allow_partial=body.allow_partial, plan_only=plan_only)


@router.post("/plan", status_code=201)
def plan(body: RunRequest, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    """A dry run: the packs, the calls, the cost estimate and any budget that blocks it. Nothing is sent to a
    model. The plan is kept, so a later run can be compared with what was planned."""
    return svc.run_out(_start(db, user, body, plan_only=True))


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def create(body: RunRequest, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    run = _start(db, user, body, plan_only=False)
    if run.status == "queued":
        dispatch(run)
        db.refresh(run)
    return svc.run_out(run)


@router.get("/runs", response_model=Page[dict])
def history(knowledge_object_id: UUID | None = None, status_: str | None = None, p: PaginationParams = Depends(),
            sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(SynthesisRun).where(SynthesisRun.organization_id == user.organization_id)
    if knowledge_object_id:
        stmt = stmt.where(SynthesisRun.knowledge_object_id == knowledge_object_id)
    if status_:
        stmt = stmt.where(SynthesisRun.status == status_)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, SynthesisRun, sort, default_field="created_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.run_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.run_out(_get(db, user.organization_id, run_id))


@router.get("/runs/{run_id}/units", response_model=Page[dict])
def units(run_id: UUID, unit_status: str | None = None, p: PaginationParams = Depends(), user: User = Reader,
          db: Session = Depends(get_db)):
    run = _get(db, user.organization_id, run_id)
    stmt = select(SynthesisUnit).where(SynthesisUnit.run_id == run.id)
    if unit_status:
        stmt = stmt.where(SynthesisUnit.status == unit_status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(SynthesisUnit.unit_key).limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.unit_out(u) for u in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/runs/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
def resume(run_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    run = _get(db, user.organization_id, run_id)
    if not run.ai_job_keys:
        raise HTTPException(409, "This run never started (blocked before any model call); create a new run.")
    if run.status not in ("blocked", "queued", "running"):
        raise HTTPException(409, f"A {run.status} run cannot be resumed.")
    job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                         AIJob.job_key == run.ai_job_keys[-1])).scalar_one()
    if job.status in ("blocked", "paused"):
        job.status = "queued"
    run.status, run.failure_reason = "queued", None
    db.commit()
    dispatch(run)
    db.refresh(run)
    return svc.run_out(run)


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    run = _get(db, user.organization_id, run_id)
    if run.status in ("completed", "completed_with_gaps", "failed", "cancelled"):
        raise HTTPException(409, f"A {run.status} run cannot be cancelled.")
    for key in run.ai_job_keys:
        job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                             AIJob.job_key == key)).scalar_one_or_none()
        if job is not None and job.status not in ("completed", "completed_with_failures", "cancelled"):
            ai_job_service.request_control(db, job, "cancel")
    run.status = "cancelled"
    db.commit()
    return svc.run_out(run)


@router.post("/runs/{run_id}/publish", status_code=201)
def publish(run_id: UUID, title: str | None = None, security_reviewed: bool = False, user: User = Editor,
            db: Session = Depends(get_db)) -> dict:
    """`security_reviewed=true` confirms that a person read the items flagged by the prompt-injection checks
    (ADR-126). Only an owner or admin can give that confirmation; it is recorded in the audit log."""
    run = _get(db, user.organization_id, run_id)
    reviewer = None
    if security_reviewed:
        if user.role not in ADMIN_ROLES:
            raise HTTPException(403, "Only an owner or admin can confirm a prompt-safety review.")
        reviewer = user
    return svc.to_publication(db, run, title=title, security_reviewed_by=reviewer)
