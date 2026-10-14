"""Coverage Audit API (§17–§23, §71–§73). Reads are cheap: the Dashboard reads a prepared audit row (§77)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.coverage_audit import CoverageAudit
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import coverage_audit_service as svc

router = APIRouter(tags=["coverage-audit"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
Reader = Depends(get_current_user)


@router.get("/knowledge/{knowledge_object_id}/coverage")
def topic_coverage(knowledge_object_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    """The prepared audit. Never recalculates on a page load."""
    return svc.current_view(db, organization_id=user.organization_id, scope="topic",
                            knowledge_object_id=knowledge_object_id)


@router.post("/knowledge/{knowledge_object_id}/coverage/run", status_code=201)
def run_topic_coverage(knowledge_object_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.audit_out(svc.run_topic_audit(db, organization_id=user.organization_id,
                                             knowledge_object_id=knowledge_object_id, trigger="manual"))


@router.get("/categories/{category_id}/coverage")
def category_coverage(category_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.current_view(db, organization_id=user.organization_id, scope="category", category_id=category_id)


@router.post("/categories/{category_id}/coverage/run", status_code=201)
def run_category_coverage(category_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.audit_out(svc.run_category_audit(db, organization_id=user.organization_id,
                                                category_id=category_id, trigger="manual"))


@router.get("/coverage-audits", response_model=Page[dict])
def history(p: PaginationParams = Depends(), sort: SortParams = Depends(), scope: str | None = None,
            status: str | None = None, knowledge_object_id: UUID | None = None, category_id: UUID | None = None,
            user: User = Reader, db: Session = Depends(get_db)):
    """§24 — every run is kept, so how coverage moved stays auditable."""
    stmt = select(CoverageAudit).where(CoverageAudit.organization_id == user.organization_id)
    if scope:
        stmt = stmt.where(CoverageAudit.scope == scope)
    if status:
        stmt = stmt.where(CoverageAudit.status == status)
    if knowledge_object_id:
        stmt = stmt.where(CoverageAudit.knowledge_object_id == knowledge_object_id)
    if category_id:
        stmt = stmt.where(CoverageAudit.category_id == category_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, CoverageAudit, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.audit_out(a) for a in rows], total=total, limit=p.limit, offset=p.offset)
