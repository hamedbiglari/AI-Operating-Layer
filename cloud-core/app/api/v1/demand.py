"""Demand Intelligence API (REQ-DI-001..003). Tenant-scoped; writes need an editor role."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.demand import DEMAND_SOURCES, DemandSignal
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import demand_service

router = APIRouter(prefix="/demand", tags=["demand-intelligence"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
MAX_UPLOAD = 10 * 1024 * 1024


def _out(s: DemandSignal) -> dict:
    return {k: getattr(s, k) for k in (
        "id", "source_type", "query_text", "normalized_query", "impressions", "clicks", "ctr", "position", "page",
        "country", "device", "searches", "zero_result_searches", "period_start", "period_end", "observed_at", "status",
        "information_need", "research_task_id", "created_at")}


@router.get("/signals", response_model=Page[dict])
def list_signals(p: PaginationParams = Depends(), sort: SortParams = Depends(), source_type: str | None = None,
                 status: str | None = None, q: str | None = None, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if source_type and source_type not in DEMAND_SOURCES:
        raise HTTPException(422, f"source_type must be one of {', '.join(DEMAND_SOURCES)}")
    stmt = select(DemandSignal).where(DemandSignal.organization_id == user.organization_id)
    if source_type:
        stmt = stmt.where(DemandSignal.source_type == source_type)
    if status:
        stmt = stmt.where(DemandSignal.status == status)
    if q:
        stmt = stmt.where(DemandSignal.normalized_query.contains(q.strip().lower()))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, DemandSignal, sort, default_field="observed_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/sync/internal-search")
def sync_internal(user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return demand_service.sync_internal_search(db, organization_id=user.organization_id)


@router.post("/import/gsc-export", status_code=201)
async def import_gsc(file: UploadFile = File(...), period_label: str | None = Form(None), user: User = Editor,
                     db: Session = Depends(get_db)) -> dict:
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File larger than 10 MB.")
    return demand_service.import_gsc_export(db, organization_id=user.organization_id, content=content,
                                            period_label=period_label)


@router.get("/connections")
def connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return demand_service.list_connections(db, organization_id=user.organization_id)


class ConnectIn(BaseModel):
    property_ref: str | None = Field(default=None, max_length=500)


@router.post("/connections/{source}/connect")
def connect(source: str, body: ConnectIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    r = demand_service.connect(db, organization_id=user.organization_id, source=source, property_ref=body.property_ref)
    return {"source_type": r.source_type, "status": r.status, "last_error": r.last_error}


class PromoteIn(BaseModel):
    signal_ids: list[UUID] = Field(min_length=1, max_length=200)


@router.post("/signals/promote", status_code=201)
def promote(body: PromoteIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return demand_service.promote(db, organization_id=user.organization_id, signal_ids=body.signal_ids,
                                  actor_user_id=user.id)
