"""
Demand Intelligence service (REQ-DI-001..003, ADR-099).

Sources stay distinct; everything becomes a DemandSignal:
  internal_search  <- first-party search events (telemetry, Phase 13)
  gsc_export       <- a Search Console performance export uploaded by the owner
  gsc / ga4        <- live OAuth connectors: BLOCKED_EXTERNAL_DEPENDENCY until
                      OAuth client credentials exist (never simulated)
Demand -> information need -> research task (traceable via research_task_id).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.demand import CONNECTABLE_SOURCES, DemandConnection, DemandSignal
from app.models.enums import ResearchMode
from app.services import research_project_service, research_task_service, search_demand_service
from app.services.keyword_service import normalize

MAX_IMPORT_ROWS = 50_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert(db: Session, org: UUID, source: str, key: str, values: dict) -> tuple[DemandSignal, bool]:
    row = db.execute(select(DemandSignal).where(DemandSignal.organization_id == org, DemandSignal.source_type == source,
                                                DemandSignal.dedupe_key == key)).scalar_one_or_none()
    created = row is None
    if created:
        row = DemandSignal(organization_id=org, source_type=source, dedupe_key=key, status="new", **values)
        db.add(row)
    else:
        for k, v in values.items():
            setattr(row, k, v)
    return row, created


def sync_internal_search(db: Session, *, organization_id: UUID) -> dict:
    """Aggregate real first-party search events into internal_search signals."""
    rows, total = search_demand_service.top_terms(db, organization_id=organization_id, limit=10_000)
    created = updated = 0
    for r in rows:
        norm = r["normalized_query"] or normalize(r["query_text"])
        _, is_new = _upsert(db, organization_id, "internal_search", norm, {
            "query_text": r["query_text"][:500], "normalized_query": norm[:500],
            "searches": int(r["search_count"]), "zero_result_searches": int(r["zero_result_count"] or 0),
            "observed_at": r["last_searched_at"] or _now(),
            "raw": {"query_id": str(r["query_id"]), "search_count": int(r["search_count"]),
                    "zero_result_count": int(r["zero_result_count"] or 0)}})
        created += is_new
        updated += not is_new
    db.commit()
    return {"source_type": "internal_search", "created": created, "updated": updated, "terms_seen": total}


def _num(v: str | None, kind=float):  # noqa: ANN001, ANN202
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip().replace(",", "").rstrip("%")
    try:
        return kind(Decimal(s)) if kind is not int else int(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def import_gsc_export(db: Session, *, organization_id: UUID, content: bytes, period_label: str | None = None) -> dict:
    """Import a Search Console 'Queries' performance export (CSV). Columns are matched
    case-insensitively: Query/Top queries, Clicks, Impressions, CTR, Position. The raw row is kept."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file must be UTF-8 CSV.") from None
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
    qcol = cols.get("query") or cols.get("top queries") or cols.get("queries")
    if not qcol:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No 'Query' / 'Top queries' column found.")
    created = updated = skipped = 0
    ctr_is_percent = True
    for i, row in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"More than {MAX_IMPORT_ROWS} rows.")
        q = (row.get(qcol) or "").strip()
        if not q:
            skipped += 1
            continue
        norm = normalize(q)
        ctr_raw = row.get(cols.get("ctr", ""), None) if cols.get("ctr") else None
        ctr = _num(ctr_raw)
        if ctr is not None and ctr_is_percent and ctr_raw and str(ctr_raw).strip().endswith("%"):
            ctr = ctr / 100.0
        key = f"{norm}|{period_label or ''}"
        _, is_new = _upsert(db, organization_id, "gsc_export", key[:600], {
            "query_text": q[:500], "normalized_query": norm[:500],
            "clicks": _num(row.get(cols["clicks"]) if "clicks" in cols else None, int),
            "impressions": _num(row.get(cols["impressions"]) if "impressions" in cols else None, int),
            "ctr": ctr, "position": _num(row.get(cols["position"]) if "position" in cols else None),
            "observed_at": _now(), "raw": {k: v for k, v in row.items()},
        })
        created += is_new
        updated += not is_new
    db.commit()
    return {"source_type": "gsc_export", "created": created, "updated": updated, "skipped_empty": skipped}


def _credentials_present(source: str) -> bool:
    if source == "gsc":
        return bool(settings.GSC_OAUTH_CLIENT_ID and settings.GSC_OAUTH_CLIENT_SECRET)
    return bool(settings.GA4_OAUTH_CLIENT_ID and settings.GA4_OAUTH_CLIENT_SECRET)


def connect(db: Session, *, organization_id: UUID, source: str, property_ref: str | None) -> DemandConnection:
    if source not in CONNECTABLE_SOURCES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown connector.")
    row = db.execute(select(DemandConnection).where(DemandConnection.organization_id == organization_id,
                                                    DemandConnection.source_type == source)).scalar_one_or_none()
    if row is None:
        row = DemandConnection(organization_id=organization_id, source_type=source, status="NOT_CONNECTED", imported_rows=0)
        db.add(row)
    row.property_ref = property_ref
    if not _credentials_present(source):
        row.status = "BLOCKED_EXTERNAL_DEPENDENCY"
        row.last_error = (f"No {source.upper()} OAuth client is configured on this Cloud Core; "
                          "the connector cannot authorise. Upload a Search Console export instead, or configure OAuth.")
    else:
        # OAuth credentials exist but the authorisation-code flow has not been completed by the owner.
        row.status = "NOT_CONNECTED"
        row.last_error = "OAuth client configured; owner authorisation not completed."
    db.commit()
    db.refresh(row)
    return row


def list_connections(db: Session, *, organization_id: UUID) -> list[dict]:
    rows = {r.source_type: r for r in db.execute(select(DemandConnection).where(
        DemandConnection.organization_id == organization_id)).scalars()}
    out = []
    for s in CONNECTABLE_SOURCES:
        r = rows.get(s)
        out.append({"source_type": s, "status": r.status if r else "NOT_CONNECTED",
                    "property_ref": r.property_ref if r else None,
                    "last_sync_at": r.last_sync_at if r else None, "last_error": r.last_error if r else None,
                    "imported_rows": r.imported_rows if r else 0,
                    "oauth_configured": _credentials_present(s)})
    return out


def promote(db: Session, *, organization_id: UUID, signal_ids: list[UUID], actor_user_id: UUID) -> dict:
    """Demand -> information need -> research task (source discovery). Traceable both ways."""
    sigs = db.execute(select(DemandSignal).where(DemandSignal.organization_id == organization_id,
                                                 DemandSignal.id.in_(signal_ids))).scalars().all()
    if len(sigs) != len(set(signal_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demand signal not found.")
    project = research_project_service.create_research_project(
        db, organization_id=organization_id, name="Demand-driven research"[:300],
        objective="Answer demand signals (search / analytics) with sourced knowledge.",
        mode=ResearchMode.USER_DRIVEN, knowledge_gap_id=None, actor_user_id=actor_user_id)
    created = []
    for s in sigs:
        need = f"Searchers ask: \"{s.query_text}\"" + (
            f" ({s.zero_result_searches} searches found nothing on the site)" if s.zero_result_searches else "")
        task = research_task_service.create_research_task(
            db, organization_id=organization_id, research_project_id=project.id, task_type="source_discovery",
            query=s.query_text, actor_user_id=actor_user_id)
        s.information_need, s.research_task_id, s.status = need, task.id, "promoted"
        created.append({"signal_id": str(s.id), "research_task_id": str(task.id), "information_need": need})
    db.commit()
    return {"research_project_id": str(project.id), "tasks": created}
