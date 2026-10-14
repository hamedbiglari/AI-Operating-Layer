"""Conflict intelligence API (§21)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.security.dependencies import get_current_user, require_roles
from app.services import conflict_service as svc

router = APIRouter(prefix="/evidence-conflicts", tags=["evidence-conflicts"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))


class ReviewIn(BaseModel):
    status: Literal["unreviewed", "under_review", "partially_resolved", "resolved", "unresolvable"]
    note: str | None = Field(default=None, max_length=4000)


@router.get("", response_model=Page[dict])
def list_conflicts(p: PaginationParams = Depends(), sort: SortParams = Depends(), status: str | None = None,
                   claim_id: UUID | None = None, knowledge_object_id: UUID | None = None,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total, rows = svc.list_conflicts(db, organization_id=user.organization_id, status=status, claim_id=claim_id,
                                     knowledge_object_id=knowledge_object_id, limit=p.limit, offset=p.offset, sort=sort)
    return Page(items=[svc.out(c) for c in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/detect/{claim_id}", status_code=201)
def detect(claim_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    made = svc.detect(db, organization_id=user.organization_id, claim_id=claim_id)
    return {"created": len(made), "conflicts": [svc.out(c) for c in made]}


@router.post("/{conflict_id}/review")
def review(conflict_id: UUID, body: ReviewIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.review(db, organization_id=user.organization_id, conflict_id=conflict_id, status=body.status,
                      note=body.note, actor_user_id=user.id)
