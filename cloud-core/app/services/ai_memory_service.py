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
from app.models.ai_center import MEMORY_KINDS, MEMORY_TRANSITIONS, SINGLETON_MEMORY_KINDS, AIWorkingMemory


class InvalidMemoryTransition(ValueError):
    pass


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
    # ADR-133: what a model wrote is not validated by being written. It starts `created` and stays so
    # until a validator or a person moves it on; application-written state is current at once.
    status = "created" if created_by.startswith("execution:") else "active"
    row = AIWorkingMemory(organization_id=organization_id, job_key=job_key, kind=kind, version=version, stage=stage,
                          item_key=item_key, knowledge_object_id=knowledge_object_id, source_id=source_id,
                          document_id=document_id, content=content, content_hash=h, created_by=created_by,
                          provenance=prov, status=status)
    db.add(row)
    db.flush()
    if kind in SINGLETON_MEMORY_KINDS:
        # Only the newest state record is current; older ones are kept, marked, and point at their successor.
        for old in db.execute(select(AIWorkingMemory).where(
                AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key,
                AIWorkingMemory.kind == kind, AIWorkingMemory.id != row.id,
                AIWorkingMemory.status.in_(("created", "validated", "active")))).scalars():
            old.status, old.superseded_by_id = "superseded", row.id
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


def transition(db: Session, row: AIWorkingMemory, to: str, *, actor: str, reason: str | None = None,
               commit: bool = True) -> AIWorkingMemory:
    """ADR-133: move a memory record along its lifecycle. Only the transitions in MEMORY_TRANSITIONS exist;
    nothing here, or anywhere, turns memory into a claim — that needs evidence and the review workflow."""
    if to not in MEMORY_TRANSITIONS.get(row.status, ()):
        raise InvalidMemoryTransition(f"memory cannot move from {row.status} to {to}")
    if to == "superseded":
        raise InvalidMemoryTransition("a record is superseded only by writing its newer version")
    history = list((row.provenance or {}).get("transitions", []))
    history.append({"from": row.status, "to": to, "by": actor, "reason": reason})
    row.provenance = {**(row.provenance or {}), "transitions": history}
    row.status = to
    if commit:
        db.commit()
    return row
