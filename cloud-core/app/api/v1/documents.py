"""
Document endpoints — tenant-scoped, writes require KNOWLEDGE_EDITOR_ROLES.

Also hosts the chunk/embed/search endpoints that exercise pgvector end
to end:

  POST /documents/{id}/process       -> chunk + embed (synchronous)
  GET  /documents/{id}/chunks        -> paginated chunk list (no vectors)
  GET  /documents/{id}/chunks/{id}   -> one chunk, including its vector
  GET  /documents/chunks/search      -> pgvector nearest-neighbor search
"""

import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit import record_audit_log
from app.models.document import Document
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, DocumentConversionStatus
from app.models.document_artifact import DocumentAsset, DocumentConversion, DocumentTable
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.document import (
    DocumentArtifactsResponse,
    DocumentAssetRead,
    DocumentCreate,
    DocumentIngestionAccepted,
    DocumentIngestionJobStatus,
    DocumentRead,
    DocumentTableRead,
    DocumentUpdate,
    ProcessingRead,
    UrlIngestionRequest,
)
from app.schemas.document_chunk import (
    DocumentChunkRead,
    DocumentChunkSearchResult,
    DocumentChunkSummary,
)
from app.security.dependencies import get_current_user, require_roles
from app.workers.tasks import ingest_document_job
from app.services import (
    document_chunk_service,
    url_ingestion_service,
    document_service,
    ingestion_job_service,
    ingestion_service,
    processing_service,
    source_service,
)

logger = logging.getLogger(__name__)


def _result_field(payload: dict, key: str):
    """Reads a field from a completed job's result, or None if the job has
    not produced one yet. None means 'not yet known', never zero."""
    result = payload.get("result")
    return result.get(key) if isinstance(result, dict) else None

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=Page[DocumentRead])
def list_documents(
    source_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[DocumentRead]:
    items, total = document_service.list_documents(
        db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=DocumentRead, status_code=201)
def create_document(
    source_id: UUID,
    payload: DocumentCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Document:
    return document_service.create_document(
        db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        title=payload.title,
        content=payload.content,
        language=payload.language,
        mime_type=payload.mime_type,
        storage_path=payload.storage_path,
        actor_user_id=current_user.id,
    )


@router.get("/chunks/search", response_model=list[DocumentChunkSearchResult])
def search_chunks(
    q: str = Query(min_length=1, max_length=2000),
    document_id: UUID | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentChunkSearchResult]:
    """pgvector cosine-distance nearest-neighbor search across this
    organization's chunks. See document_chunk_service.search_similar_chunks
    for the important caveat about the placeholder embedding provider."""
    if document_id is not None:
        document_service.get_document_or_404(
            db, document_id=document_id, organization_id=current_user.organization_id
        )
    return document_chunk_service.search_similar_chunks(
        db,
        organization_id=current_user.organization_id,
        query_text=q,
        limit=limit,
        document_id=document_id,
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    return document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Document:
    document = document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    return document_service.update_document(
        db,
        document=document,
        title=payload.title,
        content=payload.content,
        language=payload.language,
        extraction_status=payload.extraction_status,
        actor_user_id=current_user.id,
    )


@router.post("/{document_id}/process", response_model=DocumentRead)
def process_document(
    document_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Document:
    """Chunk + embed this document's content synchronously. Safe to call
    more than once — each call replaces any existing chunks."""
    document, _chunks = document_chunk_service.process_document(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    return document


@router.get("/{document_id}/chunks", response_model=Page[DocumentChunkSummary])
def list_document_chunks(
    document_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[DocumentChunkSummary]:
    items, total = document_chunk_service.list_chunks(
        db,
        document_id=document_id,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkRead)
def get_document_chunk(
    document_id: UUID,
    chunk_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    # Ownership of the parent document first, then the chunk itself —
    # and confirm the chunk actually belongs to THIS document, not just
    # to this organization (a chunk ID from a sibling document in the
    # same org must still 404 here).
    document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    chunk = document_chunk_service.get_chunk_or_404(
        db, chunk_id=chunk_id, organization_id=current_user.organization_id
    )
    if chunk.document_id != document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document chunk not found")
    return chunk


# --- Phase 3 completion: file ingestion (ADR-065) ---------------------------


@router.post("/upload", response_model=DocumentIngestionAccepted,
             status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    source_id: UUID = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    language: str = Form(default="en"),
    ocr_languages: str = Form(default="eng"),
    enable_ocr: bool = Form(default=True),
    idempotency_key: str | None = Form(default=None),
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentIngestionAccepted:
    """Accepts a document and returns 202 with a durable job id (P12-02).

    Synchronous work is deliberately minimal and all of it durable:
    validate, retain the original, create the document + PENDING conversion
    rows, create the job. The expensive pipeline — MarkItDown, tables,
    images, OCR — runs in a Celery worker, because a large scanned PDF held
    an HTTP worker for minutes under the previous design.

    The original is retained BEFORE the 202, so "accepted" means the bytes
    are safe rather than merely that a message was queued.

    An identical upload returns the SAME job with `job_created: false`
    instead of starting a second ingestion (P12-04).
    """
    source_service.get_source_or_404(
        db, source_id=source_id, organization_id=current_user.organization_id
    )
    from app.ingestion.providers.ocr import safe_languages

    try:
        ocr_languages = safe_languages(ocr_languages)          # security audit SEC-15
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    data = await file.read(ingestion_service.MAX_UPLOAD_BYTES + 1)
    filename = file.filename or "upload"

    document, conversion = ingestion_service.persist_source_only(
        db, organization_id=current_user.organization_id,
        actor_user_id=current_user.id, source_id=source_id,
        filename=filename, data=data, title=title, language=language,
    )

    job, created = ingestion_job_service.create_ingestion_job(
        db,
        organization_id=current_user.organization_id,
        site_id=None,
        document_id=document.id,
        conversion_id=conversion.id,
        source_hash=conversion.source_hash,
        actor_user_id=current_user.id,
        idempotency_key=idempotency_key,
        ocr_languages=ocr_languages,
        enable_ocr=enable_ocr,
    )
    db.commit()
    db.refresh(job)

    if created:
        # Dispatched AFTER commit: enqueuing inside the transaction risks a
        # worker reading a job row that is not yet visible to it.
        try:
            ingest_document_job.delay(str(job.id))
        except Exception as exc:  # broker unavailable
            # The job row survives and the stalled-job sweeper reclaims it.
            # A failed enqueue must not lose the upload.
            logger.warning("ingestion enqueue failed for job %s: %s", job.id, exc)

    return DocumentIngestionAccepted(
        job_id=job.id,
        status=job.status,
        job_type=job.job_type,
        job_created=created,
        source_hash=conversion.source_hash,
        storage_path_recorded=bool(conversion.storage_path),
        created_at=job.created_at,
        status_url=f"/api/v1/documents/ingestion-jobs/{job.id}",
        document_id=document.id,
        conversion_id=conversion.id,
    )


@router.get("/{document_id}/markdown", response_class=PlainTextResponse)
def get_document_markdown(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """The canonical Markdown artifact as text/markdown.

    This is the DERIVED artifact (ADR-065). The original file remains
    authoritative; `source_hash` on the conversion record ties them."""
    document = document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    if not document.content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No canonical Markdown artifact exists for this document.",
        )
    return PlainTextResponse(content=document.content, media_type="text/markdown; charset=utf-8")


@router.get("/{document_id}/processing", response_model=ProcessingRead)
def get_document_processing(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessingRead:
    """The Processing view: each pipeline stage's state as far as the backend
    records it, and what the document has produced. One call per document."""
    return ProcessingRead(**processing_service.get_processing(
        db, document_id=document_id, organization_id=current_user.organization_id))


@router.get("/{document_id}/artifacts", response_model=DocumentArtifactsResponse)
def get_document_artifacts(
    document_id: UUID,
    conversion_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentArtifactsResponse:
    """Structured tables and image assets, including images that were found
    but NOT interpreted — which is information, not an omission.

    v4 (ADR-122): rows belong to the extraction that produced them. By default the CURRENT extraction's
    rows are returned; `conversion_id` selects an earlier one, which stays readable after a reprocess.
    Rows written before migration 0037 carry no extraction and are returned when the current one has none."""
    document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    if conversion_id is None:
        current = ingestion_service.current_conversion(
            db, organization_id=current_user.organization_id, document_id=document_id)
        conversion_id = current.id if current is not None else None

    def _scoped(model):
        base = select(model).where(model.organization_id == current_user.organization_id,
                                   model.document_id == document_id)
        if conversion_id is not None:
            own = db.execute(base.where(model.conversion_id == conversion_id)).scalars().first()
            return base.where(model.conversion_id == conversion_id) if own is not None                 else base.where(model.conversion_id.is_(None))
        return base

    tables = db.execute(_scoped(DocumentTable).order_by(DocumentTable.position.asc())).scalars().all()
    assets = db.execute(_scoped(DocumentAsset).order_by(DocumentAsset.created_at.asc())).scalars().all()
    return DocumentArtifactsResponse(
        document_id=document_id,
        tables=[DocumentTableRead.model_validate(t) for t in tables],
        assets=[DocumentAssetRead.model_validate(a) for a in assets],
    )


@router.get("/{document_id}/original")
def get_document_original(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Returns the retained ORIGINAL bytes (P12-01, ADR-070).

    Two independent tenant checks, deliberately: the document row is
    tenant-scoped, and the store refuses any path outside the caller's
    tenant directory. Either alone would be sufficient today; together they
    mean a wrong database row cannot become a cross-tenant file read."""
    from app.ingestion.storage import get_store

    document_service.get_document_or_404(
        db, document_id=document_id, organization_id=current_user.organization_id
    )
    conversion = db.execute(
        select(DocumentConversion).where(
            DocumentConversion.organization_id == current_user.organization_id,
            DocumentConversion.document_id == document_id,
        ).order_by(DocumentConversion.created_at.desc())
    ).scalars().first()

    if conversion is None or not conversion.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No retained original exists for this document.",
        )
    try:
        payload = get_store().get(
            organization_id=current_user.organization_id,
            storage_path=conversion.storage_path,
        )
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The retained original is no longer available.",
        ) from None

    return Response(
        content=payload,
        media_type=conversion.source_mime_type or "application/octet-stream",
        headers={
            # `attachment` so a stored HTML/SVG original cannot execute in
            # the caller's origin if opened in a browser.
            "Content-Disposition": f'attachment; filename="{conversion.source_hash[:16]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/ingestion-jobs/{job_id}", response_model=DocumentIngestionJobStatus)
def get_ingestion_job_status(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentIngestionJobStatus:
    """Polling endpoint for an ingestion job (P12-02/P12-03).

    `status` is the JOB outcome; `conversion_status` is the DOCUMENT
    outcome. A job can SUCCEED while reporting that the file could not be
    converted — those are different facts and collapsing them would hide a
    failed conversion behind a green job."""
    from app.models.sync_job import SyncJob

    job = db.execute(
        select(SyncJob).where(
            SyncJob.id == job_id,
            SyncJob.organization_id == current_user.organization_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")

    payload = job.payload or {}
    document_id = payload.get("document_id")
    conversion = None
    if document_id:
        conversion = db.execute(
            select(DocumentConversion).where(
                DocumentConversion.organization_id == current_user.organization_id,
                DocumentConversion.document_id == UUID(document_id),
            ).order_by(DocumentConversion.created_at.desc())
        ).scalars().first()

    return DocumentIngestionJobStatus(
        job_id=job.id,
        status=job.status,
        conversion_status=conversion.conversion_status if conversion else None,
        attempts=job.attempts,
        document_id=UUID(document_id) if document_id else None,
        conversion_id=conversion.id if conversion else None,
        extraction_level=int(conversion.extraction_level.value) if conversion else None,
        table_count=conversion.table_count if conversion else None,
        image_count=conversion.image_count if conversion else None,
        ocr_block_count=conversion.ocr_block_count if conversion else None,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        # The canonical job service nests the outcome under
        # payload["result"]; returning the whole payload would bury it and
        # also expose internal job wiring to the caller.
        result=(payload.get("result") if job.status.value == "succeeded" else None),
    )


# P14-CORRECTION-001 (Phase 15): manual retry — see
# docs/phase15/ADR-MANUAL-RETRY.md and
# app/services/ingestion_job_service.retry_job for the model and
# idempotency rationale.
@router.post("/ingestion-jobs/{job_id}/retry", response_model=DocumentIngestionJobStatus)
def retry_ingestion_job(
    job_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentIngestionJobStatus:
    """Manually retry a failed ingestion job.

    Same authorization tier as creating one (`ingest-url`) — retrying is
    a mutation with the same blast radius as the original submission, not
    a read. Tenant ownership is enforced inside the service function
    itself (the lookup is WHERE organization_id = caller's own), so a
    job belonging to another tenant returns exactly the same 404 as a
    job that does not exist at all — no distinguishing signal either way.
    """
    from app.services.ingestion_job_service import RetryNotEligible, retry_job

    try:
        job, dispatched = retry_job(
            db, job_id=job_id, organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
        )
    except RetryNotEligible as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is {exc.current_status.value}; only a failed job can be retried.",
        ) from None

    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")

    if dispatched:
        try:
            ingest_document_job.delay(str(job.id))
        except Exception as exc:
            logger.warning("manual retry enqueue failed for job %s: %s", job.id, exc)

    return get_ingestion_job_status(job_id, current_user=current_user, db=db)


@router.post("/ingest-url", response_model=DocumentIngestionAccepted,
             status_code=status.HTTP_202_ACCEPTED)
def ingest_url(
    payload: UrlIngestionRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentIngestionAccepted:
    """Queues a URL for ingestion (P12-07, ADR-072).

    **No network activity happens in this request.** The fetch runs in the
    worker, behind the SSRF guard in `app/ingestion/url_source.py`. That
    placement is a security property, not just a latency one: fetching here
    would make the API itself the SSRF probe and its timing observable to
    the caller, which is the difference between a rejection and a port
    scanner.

    The URL is validated structurally now so an obviously bad request fails
    fast with a clear 422, but the authoritative checks — DNS resolution,
    per-hop redirect validation, IP pinning — happen at fetch time, because
    DNS can change between validation and connection.
    """
    from app.ingestion.url_source import UrlRejected, validate_url

    source_service.get_source_or_404(
        db, source_id=payload.source_id, organization_id=current_user.organization_id
    )

    try:
        validate_url(payload.url)
    except UrlRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None

    job, created = url_ingestion_service.create_url_ingestion_job(
        db,
        organization_id=current_user.organization_id,
        source_id=payload.source_id,
        url=payload.url,
        title=payload.title,
        language=payload.language,
        idempotency_key=payload.idempotency_key,
    )
    record_audit_log(
        db, organization_id=current_user.organization_id, user_id=current_user.id,
        action="document.url_ingestion_queued", resource_type="sync_job",
        resource_id=job.id,
        new_value={"normalized_url": url_ingestion_service.normalize_url(payload.url),
                   "job_created": created},
    )
    db.commit()
    db.refresh(job)

    if created:
        try:
            ingest_document_job.delay(str(job.id))
        except Exception as exc:
            logger.warning("url ingestion enqueue failed for job %s: %s", job.id, exc)

    return DocumentIngestionAccepted(
        job_id=job.id,
        status=job.status,
        job_type=job.job_type,
        job_created=created,
        # No document exists yet for a URL job: nothing has been fetched.
        # The hash is of the normalized URL, which is the only identity
        # available before retrieval - and is explicitly NOT a content hash.
        source_hash=url_ingestion_service.url_idempotency_key(
            organization_id=current_user.organization_id,
            source_id=payload.source_id,
            normalized_url=url_ingestion_service.normalize_url(payload.url),
        ),
        storage_path_recorded=False,
        created_at=job.created_at,
        status_url=f"/api/v1/documents/ingestion-jobs/{job.id}",
        document_id=None,
        conversion_id=None,
    )
