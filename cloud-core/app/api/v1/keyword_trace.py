"""
Keyword traceability API (REQ-KW-004).
Every transition in the keyword→published chain is recorded here.
"""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.keyword_trace import KeywordTrace, ALL_STAGES
from app.models.user import User
from app.security.dependencies import get_current_user, require_roles
from app.models.enums import UserRole

router = APIRouter(prefix="/keyword-traces", tags=["keyword-traces"])
Editor = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))
Reader = Depends(get_current_user)


class TraceRecord(BaseModel):
    keyword_id: UUID
    research_task_id: UUID | None = None
    source_id: UUID | None = None
    evidence_id: UUID | None = None
    claim_id: UUID | None = None
    knowledge_object_id: UUID | None = None
    knowledge_version_id: int | None = None
    published_target: str | None = None
    notes: str | None = None


def _stage(trace: TraceRecord) -> str:
    for s, f in zip(
        ALL_STAGES[7::-1],
        ["published_target", "knowledge_version_id", "knowledge_object_id",
         "claim_id", "evidence_id", "source_id", "research_task_id", "keyword_id"],
    ):
        if getattr(trace, f, None) is not None:
            return s
    return "keyword"


def _owned(db: Session, org, body: TraceRecord) -> None:
    """Every referenced artifact must belong to the caller's tenant (IDOR guard):
    a trace can never point into another tenant's data."""
    from app.models.ai_center import KnowledgeKeyword
    from app.models.claim import Claim
    from app.models.evidence import Evidence
    from app.models.knowledge_object import KnowledgeObject
    from app.models.research_task import ResearchTask
    from app.models.source import Source
    checks = [(KnowledgeKeyword, body.keyword_id), (ResearchTask, body.research_task_id), (Source, body.source_id),
              (Evidence, body.evidence_id), (Claim, body.claim_id), (KnowledgeObject, body.knowledge_object_id)]
    for model, ident in checks:
        if ident is None:
            continue
        found = db.execute(select(model.id).where(model.id == ident, model.organization_id == org)).scalar_one_or_none()
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__tablename__} {ident} not found.")


_CHAIN = ["research_task_id", "source_id", "evidence_id", "claim_id", "knowledge_object_id",
          "knowledge_version_id", "published_target"]


def _contiguous(values: dict) -> None:
    """Honesty rule: a later stage may only be recorded when every earlier
    stage exists — a trace can never claim "published" while evidence or a
    claim is missing."""
    seen_gap = None
    for f in _CHAIN:
        if values.get(f) is None:
            seen_gap = seen_gap or f
        elif seen_gap:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{f} cannot be recorded before {seen_gap}.")


@router.post("", status_code=201)
def record_trace(body: TraceRecord, user: User = Editor, db: Session = Depends(get_db)):
    _owned(db, user.organization_id, body)
    # Update existing trace for same keyword+task, or create new
    existing = db.execute(
        select(KeywordTrace).where(
            KeywordTrace.organization_id == user.organization_id,
            KeywordTrace.keyword_id == body.keyword_id,
            KeywordTrace.research_task_id == body.research_task_id,
        )
    ).scalar_one_or_none()
    if existing:
        # Validate the MERGED state before touching the row (no partial write on 422).
        fields = ("source_id","evidence_id","claim_id","knowledge_object_id",
                  "knowledge_version_id","published_target","notes")
        merged = {f: (getattr(body, f, None) if getattr(body, f, None) is not None else getattr(existing, f))
                  for f in fields}
        merged["research_task_id"] = existing.research_task_id
        _contiguous(merged)
        for f in fields:
            setattr(existing, f, merged[f])
        existing.stage = _stage(existing)
        db.commit(); db.refresh(existing)
        return _fmt(existing)
    _contiguous(body.model_dump())
    row = KeywordTrace(organization_id=user.organization_id, stage=_stage(body), **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return _fmt(row)


@router.get("/keyword/{keyword_id}")
def get_traces_for_keyword(keyword_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    from app.models.ai_center import KnowledgeKeyword
    if db.execute(select(KnowledgeKeyword.id).where(KnowledgeKeyword.id == keyword_id,
                  KnowledgeKeyword.organization_id == user.organization_id)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keyword not found.")
    rows = db.execute(
        select(KeywordTrace).where(
            KeywordTrace.organization_id == user.organization_id,
            KeywordTrace.keyword_id == keyword_id,
        ).order_by(KeywordTrace.created_at.desc())
    ).scalars().all()
    return {"keyword_id": str(keyword_id), "traces": [_fmt(r) for r in rows],
            "is_complete": any(r.published_target for r in rows)}


def _fmt(r: KeywordTrace) -> dict:
    return {"id": str(r.id), "keyword_id": str(r.keyword_id), "stage": r.stage,
            "research_task_id": str(r.research_task_id) if r.research_task_id else None,
            "source_id": str(r.source_id) if r.source_id else None,
            "evidence_id": str(r.evidence_id) if r.evidence_id else None,
            "claim_id": str(r.claim_id) if r.claim_id else None,
            "knowledge_object_id": str(r.knowledge_object_id) if r.knowledge_object_id else None,
            "knowledge_version_id": r.knowledge_version_id,
            "published_target": r.published_target,
            "is_complete": r.published_target is not None,
            "created_at": r.created_at.isoformat() if r.created_at else None}
