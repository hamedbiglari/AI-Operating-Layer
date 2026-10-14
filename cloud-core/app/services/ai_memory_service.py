"""Shared AI working memory (REQ-AIC-004/005, ADR-090). Provider-agnostic,
tenant-scoped, versioned, deduplicated by content hash. Canonical in
PostgreSQL; Walrus may mirror (optional, never required)."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.memory import walrus
from app.models.ai_center import MEMORY_KINDS, AIWorkingMemory


def _hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def write(db: Session, *, organization_id: UUID, job_key: str, kind: str, content: dict, created_by: str,
          stage: str | None = None, item_key: str | None = None, knowledge_object_id: UUID | None = None,
          source_id: UUID | None = None, document_id: UUID | None = None, provenance: dict | None = None,
          commit: bool = True) -> AIWorkingMemory:
    if kind not in MEMORY_KINDS:
        raise ValueError(f"unknown memory kind {kind}")
    h = _hash(content)
    existing = db.execute(select(AIWorkingMemory).where(
        AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key,
        AIWorkingMemory.kind == kind, AIWorkingMemory.content_hash == h)).scalar_one_or_none()
    if existing is not None:
        return existing   # idempotent: the same content is never stored twice
    version = (db.execute(select(func.max(AIWorkingMemory.version)).where(
        AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key,
        AIWorkingMemory.kind == kind)).scalar_one() or 0) + 1
    prov = dict(provenance or {})
    row = AIWorkingMemory(organization_id=organization_id, job_key=job_key, kind=kind, version=version, stage=stage,
                          item_key=item_key, knowledge_object_id=knowledge_object_id, source_id=source_id,
                          document_id=document_id, content=content, content_hash=h, created_by=created_by, provenance=prov)
    db.add(row)
    db.flush()
    prov["semantic_mirror"] = "walrus" if walrus.mirror_write(organization_id, {"id": str(row.id), **content}) else "none"
    row.provenance = prov
    if commit:
        db.commit()
    return row


def latest(db: Session, *, organization_id: UUID, job_key: str, kind: str) -> AIWorkingMemory | None:
    return db.execute(select(AIWorkingMemory).where(
        AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key,
        AIWorkingMemory.kind == kind).order_by(AIWorkingMemory.version.desc()).limit(1)).scalar_one_or_none()


def list_items(db: Session, *, organization_id: UUID, job_key: str, kind: str | None = None,
               limit: int = 100, offset: int = 0, sort=None) -> tuple[list[AIWorkingMemory], int]:
    q = [AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key]
    if kind:
        q.append(AIWorkingMemory.kind == kind)
    total = db.execute(select(func.count()).select_from(AIWorkingMemory).where(*q)).scalar_one()
    from app.schemas.common import SortDirection, apply_sort

    stmt = apply_sort(select(AIWorkingMemory).where(*q), AIWorkingMemory, sort, default_field="created_at",
                      default_dir=SortDirection.ASC)
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(rows), total
