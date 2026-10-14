"""Memory Center API (§9): search, versions, compare, export."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams
from app.security.dependencies import get_current_user, require_roles
from app.services import memory_center_service as svc

router = APIRouter(prefix="/memory", tags=["memory-center"])


@router.get("/search", response_model=Page[dict])
def search(p: PaginationParams = Depends(), q: str | None = Query(default=None, max_length=200),
           kind: str | None = None, job_key: str | None = None, knowledge_object_id: UUID | None = None,
           created_from: datetime | None = None, created_to: datetime | None = None, latest_only: bool = False,
           sort: Literal["created_at", "job_key", "kind", "version"] = "created_at",
           direction: Literal["asc", "desc"] = "desc",
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total, items = svc.search(db, organization_id=user.organization_id, q=q, kind=kind, job_key=job_key,
                              knowledge_object_id=knowledge_object_id, created_from=created_from, created_to=created_to,
                              latest_only=latest_only, sort=sort, direction=direction, limit=p.limit, offset=p.offset)
    return Page(items=items, total=total, limit=p.limit, offset=p.offset)


@router.get("/items/{job_key}/{kind}/versions")
def versions(job_key: str, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return svc.versions(db, organization_id=user.organization_id, job_key=job_key, kind=kind)


@router.get("/items/{job_key}/{kind}/compare")
def compare(job_key: str, kind: str, left: int, right: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    return svc.compare(db, organization_id=user.organization_id, job_key=job_key, kind=kind, left=left, right=right)


@router.get("/export.{fmt}")
def export(fmt: Literal["json", "jsonl", "csv", "md", "zip"], job_key: str | None = None, kind: str | None = None,
           knowledge_object_id: UUID | None = None, created_from: datetime | None = None,
           created_to: datetime | None = None, user: User = Depends(require_roles(*ADMIN_ROLES)),
           db: Session = Depends(get_db)) -> Response:
    from app.services.audit import record_audit_log

    scope = {"job_key": job_key, "kind": kind, "knowledge_object_id": knowledge_object_id,
             "created_from": created_from, "created_to": created_to}
    body, media, name = svc.export(db, organization_id=user.organization_id, fmt=fmt, scope=scope)
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="ai_memory.export",
                     resource_type="organization", resource_id=user.organization_id,
                     new_value={"format": fmt, "bytes": len(body), "scope": {k: str(v) for k, v in scope.items() if v}})
    db.commit()
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                     "Cache-Control": "no-store"})
