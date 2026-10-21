"""
Document intelligence API (prompt v4.0 §5–§12, §38, §54–§56; ADR-122).

    GET  /documents/extraction/providers           what each provider can do, and whether it is usable
    GET  /documents/extraction/stale               documents whose current extraction came from older
                                                   or different technology (§56 controlled reprocessing)
    GET  /documents/{id}/conversions               every extraction of the document, current and superseded
    GET  /documents/{id}/elements                  the canonical representation (filter by page / type)
    GET  /documents/{id}/render/{format}           markdown · mmd · html · latex · json, all from the CDR
    POST /documents/{id}/reprocess                 a new extraction of the retained original (202 + job)
    GET  /documents/{id}/pages/{page}/claims       every claim whose evidence was read on that page

Two-segment paths under `/documents/extraction/...` are deliberate: a single segment would be captured by
`GET /documents/{document_id}` and rejected as a malformed UUID.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ingestion import render as renderer
from app.ingestion.cdr import CanonicalDocument, Confidence, Element, Page
from app.ingestion.providers import configured_order, registry
from app.models.document_artifact import DocumentConversion
from app.models.document_element import DocumentElement
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page as PageOf, PaginationParams
from app.security.dependencies import get_current_user, require_roles
from app.services import document_service, ingestion_job_service, ingestion_service, knowledge_query_service
from app.workers.tasks import ingest_document_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["document-intelligence"])
Reader = Depends(get_current_user)
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))


def conversion_out(c: DocumentConversion) -> dict:
    return {
        "id": str(c.id), "document_id": str(c.document_id), "is_current": c.is_current,
        "superseded_at": c.superseded_at, "trigger": c.trigger, "created_at": c.created_at,
        "completed_at": c.completed_at, "processing_state": c.processing_state,
        "needs_review": c.needs_review, "review_reasons": c.review_reasons,
        "layout_provider": c.layout_provider, "layout_provider_version": c.layout_provider_version,
        "converter": {"name": c.converter_name, "version": c.converter_version,
                      "status": c.conversion_status.value},
        "document_class": c.document_class, "page_count": c.page_count,
        "unprocessed_pages": c.unprocessed_pages,
        # §10 — six separate figures; None = not measured, never zero
        "confidence": {"text": c.text_confidence, "layout": c.layout_confidence, "table": c.table_confidence,
                       "equation": c.equation_confidence, "figure": c.figure_confidence,
                       "overall": c.overall_confidence},
        "candidates": c.candidates, "provider_config": c.provider_config,
        "has_provider_raw_output": c.provider_raw_output is not None,
        "warnings": (c.warnings or {}).get("messages", []),
    }


def element_out(e: DocumentElement) -> dict:
    return {"id": str(e.id), "conversion_id": str(e.conversion_id), "element_type": e.element_type,
            "reading_order": e.reading_order, "page": e.page, "block_id": e.block_id,
            "parent_block_id": e.parent_block_id, "level": e.level, "text": e.text,
            "normalized_text": e.normalized_text, "language": e.language, "script": e.script,
            "direction": e.direction, "bbox": e.bbox, "lines": e.lines, "attributes": e.attributes,
            "confidence": e.confidence, "method": e.method}


def _conversion(db: Session, org: UUID, document_id: UUID, conversion_id: UUID | None) -> DocumentConversion:
    document_service.get_document_or_404(db, document_id=document_id, organization_id=org)
    if conversion_id is None:
        conv = ingestion_service.current_conversion(db, organization_id=org, document_id=document_id)
    else:
        conv = db.execute(select(DocumentConversion).where(
            DocumentConversion.id == conversion_id, DocumentConversion.organization_id == org,
            DocumentConversion.document_id == document_id)).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No extraction exists for this document.")
    return conv


def load_cdr(db: Session, conv: DocumentConversion) -> CanonicalDocument:
    """Rebuild the in-memory CDR from its rows, so every renderer reads the persisted representation."""
    rows = db.execute(select(DocumentElement).where(DocumentElement.conversion_id == conv.id)
                      .order_by(DocumentElement.reading_order)).scalars().all()
    pages = sorted({r.page for r in rows if r.page})
    doc = CanonicalDocument(
        provider=conv.layout_provider or "unknown", provider_version=conv.layout_provider_version or "unknown",
        document_class=conv.document_class or "unknown", page_count=conv.page_count,
        pages=[Page(number=p) for p in pages], unprocessed_pages=list(conv.unprocessed_pages or []),
        review_reasons=list(conv.review_reasons or []),
        confidence=Confidence(text=conv.text_confidence, layout=conv.layout_confidence,
                              table=conv.table_confidence, equation=conv.equation_confidence,
                              figure=conv.figure_confidence))
    doc.elements = [Element(element_type=r.element_type, page=r.page, reading_order=r.reading_order,
                            text=r.text, normalized_text=r.normalized_text, bbox=r.bbox, block_id=r.block_id,
                            parent_block_id=r.parent_block_id, level=r.level, language=r.language,
                            script=r.script, direction=r.direction, confidence=r.confidence, method=r.method,
                            attributes=dict(r.attributes or {}), lines=list(r.lines or [])) for r in rows]
    return doc


# ---------------------------------------------------------------------- technology
@router.get("/extraction/providers")
def providers(user: User = Reader) -> dict:
    reg = registry()
    order = configured_order()
    return {"order": order,
            "providers": [reg[n].describe() for n in order if n in reg],
            "vision": {"name": "vision", "available": False,
                       "reason": "no vision-capable adapter: the LLM adapter contract is text-only"},
            "note": ("Capabilities are declared by each provider, not measured. Benchmarks measure; a provider "
                     "is never assumed better because it is newer or because its vendor says so.")}


@router.get("/extraction/stale")
def stale_extractions(provider: str | None = None, user: User = Reader, db: Session = Depends(get_db),
                      p: PaginationParams = Depends()) -> dict:
    """§56 — documents whose CURRENT extraction was produced by technology other than what would be used
    now: no canonical representation at all (pre-v4), or an older version of the provider."""
    reg = registry()
    current_versions = {n: prov.version for n, prov in reg.items()}
    convs = db.execute(select(DocumentConversion).where(
        DocumentConversion.organization_id == user.organization_id,
        DocumentConversion.is_current.is_(True))).scalars().all()
    stale = []
    for c in convs:
        if provider and c.layout_provider != provider:
            continue
        if c.layout_provider is None:
            why = "no canonical representation (extracted before v4 or every provider failed)"
        elif c.layout_provider in current_versions and c.layout_provider_version != current_versions[c.layout_provider]:
            why = f"{c.layout_provider} {c.layout_provider_version} → now {current_versions[c.layout_provider]}"
        else:
            continue
        stale.append({"document_id": str(c.document_id), "conversion_id": str(c.id),
                      "layout_provider": c.layout_provider, "layout_provider_version": c.layout_provider_version,
                      "processing_state": c.processing_state, "reason": why})
    return {"total": len(stale), "items": stale[p.offset:p.offset + p.limit], "current_versions": current_versions}


# ---------------------------------------------------------------------- one document
@router.get("/{document_id}/conversions")
def conversions(document_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    document_service.get_document_or_404(db, document_id=document_id, organization_id=user.organization_id)
    rows = db.execute(select(DocumentConversion).where(
        DocumentConversion.organization_id == user.organization_id,
        DocumentConversion.document_id == document_id).order_by(DocumentConversion.created_at.desc())).scalars().all()
    return [conversion_out(c) for c in rows]


@router.get("/{document_id}/elements", response_model=PageOf[dict])
def elements(document_id: UUID, conversion_id: UUID | None = None, page: int | None = Query(default=None, ge=1),
             element_type: str | None = None, p: PaginationParams = Depends(), user: User = Reader,
             db: Session = Depends(get_db)):
    conv = _conversion(db, user.organization_id, document_id, conversion_id)
    stmt = select(DocumentElement).where(DocumentElement.conversion_id == conv.id,
                                         DocumentElement.organization_id == user.organization_id)
    if page is not None:
        stmt = stmt.where(DocumentElement.page == page)
    if element_type:
        stmt = stmt.where(DocumentElement.element_type == element_type)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(DocumentElement.reading_order).limit(p.limit).offset(p.offset)).scalars().all()
    return PageOf(items=[element_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/{document_id}/render/{fmt}")
def render(document_id: UUID, fmt: str, conversion_id: UUID | None = None, user: User = Reader,
           db: Session = Depends(get_db)) -> Response:
    conv = _conversion(db, user.organization_id, document_id, conversion_id)
    if fmt == "provider-mmd":
        if conv.provider_raw_output is None:
            raise HTTPException(404, "This extraction has no verbatim provider output.")
        return Response(conv.provider_raw_output, media_type="text/markdown; charset=utf-8",
                        headers={"X-Content-Type-Options": "nosniff"})
    doc = load_cdr(db, conv)
    if not doc.elements:
        raise HTTPException(404, "This extraction has no canonical representation to render.")
    try:
        body = renderer.render(doc, fmt)
    except renderer.UnsupportedFormat as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED if fmt in renderer.UNAVAILABLE_FORMATS
                            else status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # Document-derived content: never sniffed, and HTML is sandboxed with no script, so a hostile document
    # cannot run code in the API's origin even if someone opens the rendering in a browser (SEC-05).
    headers = {"X-Content-Type-Options": "nosniff"}
    if fmt == "html":
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    return Response(body, media_type=renderer.MEDIA_TYPES[fmt], headers=headers)


class ReprocessRequest(BaseModel):
    providers: list[str] | None = Field(default=None, description="Provider order for this run; default = configured")
    trigger: str = Field(default="reprocess", max_length=40)
    # Tesseract codes only, e.g. "eng" or "eng+fas" (security audit SEC-15).
    ocr_languages: str = Field(default="eng", max_length=60,
                               pattern=r"^[a-z]{3}(?:_[a-z]{3,4})?(?:\+[a-z]{3}(?:_[a-z]{3,4})?){0,4}$")


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
def reprocess(document_id: UUID, body: ReprocessRequest | None = None, user: User = Editor,
              db: Session = Depends(get_db)) -> dict:
    """§38/§54 — 'Reprocess this PDF using the latest extraction technology'. The current extraction stays in
    force until the new one succeeds; the old one is then superseded, never deleted."""
    body = body or ReprocessRequest()
    known = set(registry())
    if body.providers and not set(body.providers) <= known:
        raise HTTPException(422, f"Unknown provider(s): {sorted(set(body.providers) - known)}")
    document_service.get_document_or_404(db, document_id=document_id, organization_id=user.organization_id)
    conv = ingestion_service.create_reprocess_conversion(
        db, organization_id=user.organization_id, document_id=document_id, actor_user_id=user.id,
        trigger=body.trigger)
    job, _ = ingestion_job_service.create_ingestion_job(
        db, organization_id=user.organization_id, site_id=None, document_id=document_id,
        conversion_id=conv.id, source_hash=conv.source_hash, actor_user_id=user.id,
        idempotency_key=f"reprocess:{conv.id}", ocr_languages=body.ocr_languages)
    if body.providers:
        job.payload = {**(job.payload or {}), "providers": body.providers}
    db.commit()
    try:
        ingest_document_job.delay(str(job.id))
    except Exception as exc:  # broker down: the job row survives and the sweeper reclaims it
        logger.warning("reprocess enqueue failed for job %s: %s", job.id, exc)
    return {"job_id": str(job.id), "conversion_id": str(conv.id), "status_url": f"/api/v1/documents/ingestion-jobs/{job.id}",
            "note": "The current extraction remains in force until this one succeeds."}


@router.get("/{document_id}/pages/{page}/claims")
def claims_on_page(document_id: UUID, page: int, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    """§54 — 'Show all claims derived from page 37'. Answered from evidence locations, not by searching text:
    a claim appears only if a piece of its evidence was recorded as read on that page of this document."""
    document_service.get_document_or_404(db, document_id=document_id, organization_id=user.organization_id)
    return knowledge_query_service.claims_on_page(db, organization_id=user.organization_id,
                                                  document_id=document_id, page=page)
