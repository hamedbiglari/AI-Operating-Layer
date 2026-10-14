"""
Memory Center (ADR-110, §9): search, filter, compare versions, and real exports.

Everything is tenant-scoped and read from the canonical store (PostgreSQL). Exports are produced by the
backend — never assembled in the browser — and carry provenance: who wrote each item, when, from which
execution, and which knowledge object, source or document it belongs to.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.agent_network import AgentHandoff
from app.models.ai_center import MEMORY_KINDS, AIWorkingMemory
from app.models.background_policy import MemoryProfile

EXPORT_FORMATS = ("json", "jsonl", "csv", "md", "zip")
CSV_COLUMNS = ("id", "job_key", "kind", "version", "stage", "item_key", "created_by", "created_at",
               "knowledge_object_id", "source_id", "document_id", "ai_execution_id", "content_hash", "content")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(m: AIWorkingMemory) -> dict:
    return {"id": str(m.id), "job_key": m.job_key, "kind": m.kind, "version": m.version, "stage": m.stage,
            "item_key": m.item_key, "created_by": m.created_by, "created_at": m.created_at,
            "knowledge_object_id": str(m.knowledge_object_id) if m.knowledge_object_id else None,
            "source_id": str(m.source_id) if m.source_id else None,
            "document_id": str(m.document_id) if m.document_id else None,
            "ai_execution_id": str(m.ai_execution_id) if getattr(m, "ai_execution_id", None) else None,
            "content_hash": m.content_hash, "provenance": m.provenance, "content": m.content}


def search(db: Session, *, organization_id: UUID, q: str | None, kind: str | None, job_key: str | None,
           knowledge_object_id: UUID | None, created_from: datetime | None, created_to: datetime | None,
           latest_only: bool, sort: str, direction: str, limit: int, offset: int) -> tuple[int, list[dict]]:
    if kind and kind not in MEMORY_KINDS:
        raise HTTPException(422, f"kind must be one of: {', '.join(MEMORY_KINDS)}")
    if sort not in ("created_at", "job_key", "kind", "version"):
        raise HTTPException(422, "sort must be created_at, job_key, kind or version")
    stmt = select(AIWorkingMemory).where(AIWorkingMemory.organization_id == organization_id)
    if kind:
        stmt = stmt.where(AIWorkingMemory.kind == kind)
    if job_key:
        stmt = stmt.where(AIWorkingMemory.job_key == job_key)
    if knowledge_object_id:
        stmt = stmt.where(AIWorkingMemory.knowledge_object_id == knowledge_object_id)
    if created_from:
        stmt = stmt.where(AIWorkingMemory.created_at >= created_from)
    if created_to:
        stmt = stmt.where(AIWorkingMemory.created_at <= created_to)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(AIWorkingMemory.job_key).like(needle),
                              func.lower(func.cast(AIWorkingMemory.content, __import__("sqlalchemy").Text)).like(needle)))
    if latest_only:
        newest = (select(AIWorkingMemory.job_key, AIWorkingMemory.kind, func.max(AIWorkingMemory.version).label("v"))
                  .where(AIWorkingMemory.organization_id == organization_id)
                  .group_by(AIWorkingMemory.job_key, AIWorkingMemory.kind).subquery())
        stmt = stmt.join(newest, (AIWorkingMemory.job_key == newest.c.job_key) &
                         (AIWorkingMemory.kind == newest.c.kind) & (AIWorkingMemory.version == newest.c.v))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    col = getattr(AIWorkingMemory, sort)
    stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc())
    return total, [_row(m) for m in db.execute(stmt.limit(limit).offset(offset)).scalars().all()]


def versions(db: Session, *, organization_id: UUID, job_key: str, kind: str) -> list[dict]:
    rows = db.execute(select(AIWorkingMemory).where(
        AIWorkingMemory.organization_id == organization_id, AIWorkingMemory.job_key == job_key,
        AIWorkingMemory.kind == kind).order_by(AIWorkingMemory.version)).scalars().all()
    if not rows:
        raise HTTPException(404, "No memory with that job key and kind.")
    return [_row(m) for m in rows]


def compare(db: Session, *, organization_id: UUID, job_key: str, kind: str, left: int, right: int) -> dict:
    rows = {m["version"]: m for m in versions(db, organization_id=organization_id, job_key=job_key, kind=kind)}
    for v in (left, right):
        if v not in rows:
            raise HTTPException(404, f"Version {v} does not exist.")
    a, b = rows[left], rows[right]
    ca, cb = a["content"] or {}, b["content"] or {}
    keys = sorted(set(ca) | set(cb))
    diff = [{"key": k, "before": ca.get(k), "after": cb.get(k),
             "change": "added" if k not in ca else "removed" if k not in cb else
                       ("unchanged" if ca[k] == cb[k] else "changed")} for k in keys]
    return {"job_key": job_key, "kind": kind, "left": {k: a[k] for k in ("version", "created_at", "created_by", "content_hash")},
            "right": {k: b[k] for k in ("version", "created_at", "created_by", "content_hash")},
            "identical": a["content_hash"] == b["content_hash"],
            "changed_keys": [d["key"] for d in diff if d["change"] != "unchanged"], "diff": diff}


def _collect(db: Session, organization_id: UUID, scope: dict) -> dict:
    total, items = search(db, organization_id=organization_id, q=None, kind=scope.get("kind"),
                          job_key=scope.get("job_key"), knowledge_object_id=scope.get("knowledge_object_id"),
                          created_from=scope.get("created_from"), created_to=scope.get("created_to"),
                          latest_only=False, sort="created_at", direction="asc", limit=100_000, offset=0)
    profiles = db.execute(select(MemoryProfile).where(MemoryProfile.organization_id == organization_id)).scalars().all()
    handoffs = db.execute(select(AgentHandoff).where(AgentHandoff.organization_id == organization_id)).scalars().all()
    cols = lambda r: {c.name: getattr(r, c.name) for c in r.__table__.columns}  # noqa: E731
    return {"format": "aiol-memory-export/2", "organization_id": str(organization_id), "exported_at": _now().isoformat(),
            "canonical_store": "postgresql", "scope": {k: str(v) for k, v in scope.items() if v is not None},
            "counts": {"working_memory": total, "memory_profiles": len(profiles), "agent_handoffs": len(handoffs)},
            "working_memory": items, "memory_profiles": [cols(p) for p in profiles],
            "agent_handoffs": [cols(h) for h in handoffs]}


def _markdown(doc: dict) -> str:
    """A readable Markdown rendering of the memory export (ADR-119, prompt §7/§22).

    This is a human-readable *representation*, not the canonical store: PostgreSQL holds the records, and the JSON,
    JSONL and ZIP formats carry them losslessly. Binary assets are never turned into Markdown — a record that points
    at one keeps its reference, checksum and provenance so the original can still be found. No credential is included.
    """
    def esc(x) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ")

    def block(value, depth: int = 0) -> list[str]:
        """Render a record's content as nested bullets; long strings become fenced blocks."""
        pad, out = "  " * depth, []
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (dict, list)) and v:
                    out.append(f"{pad}- **{esc(k)}**")
                    out += block(v, depth + 1)
                else:
                    out.append(f"{pad}- **{esc(k)}**: {esc(v) if v not in (None, '', [], {}) else '_empty_'}")
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, (dict, list)):
                    out.append(f"{pad}-")
                    out += block(v, depth + 1)
                else:
                    out.append(f"{pad}- {esc(v)}")
        elif isinstance(value, str) and ("\n" in value or len(value) > 300):
            out += [f"{pad}```text", value, f"{pad}```"]
        else:
            out.append(f"{pad}- {esc(value)}")
        return out

    c, L = doc["counts"], []
    L += ["# AI Operating Layer — memory export", "",
          f"- **Organization**: `{doc['organization_id']}`",
          f"- **Exported at**: {doc['exported_at']}",
          f"- **Format**: `{doc['format']}`",
          f"- **Canonical store**: {doc['canonical_store']} — this Markdown is a readable representation, not the store itself",
          f"- **Records**: {c['working_memory']} working memory · {c['memory_profiles']} memory profiles · {c['agent_handoffs']} agent handoffs"]
    if doc.get("scope"):
        L += ["- **Scope**: " + ", ".join(f"{k} = `{v}`" for k, v in doc["scope"].items())]
    L += ["", "> No credential, API key or secret is included in this export.", ""]

    L += ["## Working memory", ""]
    if not doc["working_memory"]:
        L += ["_No working-memory records in this scope._", ""]
    for m in doc["working_memory"]:
        L += [f"### {esc(m.get('kind') or 'record')} · `{esc(m.get('job_key'))}` · v{esc(m.get('version'))}", "",
              f"- **Record id**: `{esc(m.get('id'))}`",
              f"- **Created**: {esc(m.get('created_at'))}"]
        for label, key in (("Knowledge object", "knowledge_object_id"), ("Produced by", "created_by"),
                           ("Provenance", "provenance"), ("Source", "source"), ("Checksum", "checksum")):
            if m.get(key) not in (None, "", {}, []):
                L.append(f"- **{label}**: {esc(m.get(key))}")
        L += ["", "**Content**", ""]
        L += block(m.get("content")) or ["- _empty_"]
        L += [""]

    L += ["## Memory profiles", ""]
    if not doc["memory_profiles"]:
        L += ["_No memory profiles in this scope._", ""]
    for p_ in doc["memory_profiles"]:
        L += [f"### {esc(p_.get('name') or p_.get('id'))}", ""] + (block(p_) or []) + [""]

    L += ["## Agent handoffs", ""]
    if not doc["agent_handoffs"]:
        L += ["_No agent handoffs in this scope._", ""]
    for h in doc["agent_handoffs"]:
        L += [f"### `{esc(h.get('id'))}`", ""] + (block(h) or []) + [""]
    return "\n".join(L) + "\n"


def export(db: Session, *, organization_id: UUID, fmt: str, scope: dict) -> tuple[bytes, str, str]:
    """Returns (body, media type, filename). No credential or secret is ever included."""
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(422, f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    doc = _collect(db, organization_id, scope)
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    base = f"memory-export-{stamp}"
    dumps = lambda o: json.dumps(o, default=str, ensure_ascii=False)  # noqa: E731
    if fmt == "json":
        return dumps(doc).encode(), "application/json", f"{base}.json"
    if fmt == "jsonl":
        lines = [dumps({"record": "meta", **{k: v for k, v in doc.items() if k not in ("working_memory", "memory_profiles", "agent_handoffs")}})]
        lines += [dumps({"record": "working_memory", **m}) for m in doc["working_memory"]]
        lines += [dumps({"record": "memory_profile", **p}) for p in doc["memory_profiles"]]
        lines += [dumps({"record": "agent_handoff", **h}) for h in doc["agent_handoffs"]]
        return ("\n".join(lines) + "\n").encode(), "application/x-ndjson", f"{base}.jsonl"
    if fmt == "md":
        return _markdown(doc).encode(), "text/markdown; charset=utf-8", f"{base}.md"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for m in doc["working_memory"]:
            w.writerow({**{k: m.get(k) for k in CSV_COLUMNS}, "content": dumps(m.get("content"))})
        return buf.getvalue().encode("utf-8-sig"), "text/csv", f"{base}.csv"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", dumps({k: v for k, v in doc.items()
                                           if k not in ("working_memory", "memory_profiles", "agent_handoffs")}))
        z.writestr("working_memory.json", dumps(doc["working_memory"]))
        z.writestr("memory_profiles.json", dumps(doc["memory_profiles"]))
        z.writestr("agent_handoffs.json", dumps(doc["agent_handoffs"]))
        csv_body, _, _ = export(db, organization_id=organization_id, fmt="csv", scope=scope)
        z.writestr("working_memory.csv", csv_body)
        md_body, _, _ = export(db, organization_id=organization_id, fmt="md", scope=scope)
        z.writestr("memory.md", md_body)
        z.writestr("README.txt", "AI Operating Layer memory export.\nCanonical store: PostgreSQL.\n"
                                 "memory.md is a readable representation; the JSON files are the lossless copy.\n"
                                 "Contains this organization's working memory (every version), memory profiles and "
                                 "agent handoffs, with provenance. No credentials are included.\n")
    return buf.getvalue(), "application/zip", f"{base}.zip"
