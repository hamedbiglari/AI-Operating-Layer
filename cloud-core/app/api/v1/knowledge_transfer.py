"""Knowledge Transfer Packages API (prompt v5 §21, §51-53; ADR-134).

A person (or an integration acting for one) may submit a package directly; worker packages arrive through AI
jobs with `output_contract='ktp_v1'`. Either way the same validator and reconciler decide what is accepted, and
every package is listed with its per-claim verdicts so nothing that was rejected disappears silently.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.knowledge_transfer import KnowledgeTransferRecord
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import knowledge_reconciliation_service as svc

router = APIRouter(prefix="/knowledge-transfer", tags=["knowledge-transfer"])


class PackageIn(BaseModel):
    knowledge_object_id: UUID
    # The package as an object, or the exact text a worker returned.
    package: dict[str, Any] | str


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; knowledge_object_id: UUID; submitted_by: str; execution_id: UUID | None; job_key: str | None
    item_key: str | None; ktp_version: int | None; status: str; invalid_reason: str | None
    validation: dict; reconciliation: dict; created_at: datetime


class PackageDetail(PackageOut):
    raw: str = Field(description="The package exactly as received")


@router.post("/packages", response_model=PackageOut, status_code=201)
def submit(body: PackageIn, user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)), db: Session = Depends(get_db)):
    raw = body.package if isinstance(body.package, str) else json.dumps(body.package, ensure_ascii=False, sort_keys=True)
    rec = svc.ingest(db, organization_id=user.organization_id, knowledge_object_id=body.knowledge_object_id, raw=raw,
                     submitted_by=f"user:{user.id}", actor_user_id=user.id)
    return PackageOut.model_validate(rec)


@router.get("/packages", response_model=Page[PackageOut])
def list_packages(knowledge_object_id: UUID | None = None, status: str | None = None,
                  p: PaginationParams = Depends(), sort: SortParams = Depends(),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(KnowledgeTransferRecord).where(KnowledgeTransferRecord.organization_id == user.organization_id)
    if knowledge_object_id:
        q = q.where(KnowledgeTransferRecord.knowledge_object_id == knowledge_object_id)
    if status:
        q = q.where(KnowledgeTransferRecord.status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, KnowledgeTransferRecord, sort, default_field="created_at",
                                 default_dir=SortDirection.DESC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[PackageOut](items=[PackageOut.model_validate(r) for r in rows], total=total, limit=p.limit,
                            offset=p.offset)


@router.get("/packages/{package_id}", response_model=PackageDetail)
def get_package(package_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = db.execute(select(KnowledgeTransferRecord).where(
        KnowledgeTransferRecord.id == package_id,
        KnowledgeTransferRecord.organization_id == user.organization_id)).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return PackageDetail.model_validate(rec)
