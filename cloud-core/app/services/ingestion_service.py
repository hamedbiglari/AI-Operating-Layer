"""
Document ingestion service (Phase 3 completion; ADR-065, ADR-071).

TWO PHASES, and the split is the point (P12-01 + P12-02):

    persist_source_only()        HTTP request. Bounded: validate, hash,
                                 retain the original, record a PENDING
                                 conversion row. Durable before the 202.

    process_pending_conversion() Celery worker. Expensive: MarkItDown,
                                 tables, images, OCR. Reads the RETAINED
                                 original rather than re-receiving bytes.

The worker reading the retained original is the payoff from P12-01: it can
reprocess at any time, including after a converter upgrade, because the
source still exists. Earlier drafts of this module carried three other
arrangements of the same work; they were removed rather than left side by
side, because duplicate abstractions are how two code paths drift.

SECURITY: THIS IS AN UNTRUSTED-INPUT BOUNDARY (§17)

An uploaded file is hostile until proven otherwise. Validation happens
before any parser touches the bytes:

  - size ceiling, enforced while streaming, so an oversized upload is cut
    off rather than buffered whole
  - extension allow-list (deny by default)
  - magic-byte check against the claimed extension, because an extension is
    a claim by the uploader
  - quarantine directory with a generated name - the original filename is
    recorded as data and never used as a path, which is what makes
    `../../etc/passwd` and absolute paths inert

Conversion runs in Cloud Core, never in WordPress (§41).

DEDUPLICATION uses `source_hash + converter_name + converter_version`. All
three matter: the same bytes converted by a different converter version may
legitimately produce different Markdown, so reusing the old artifact after
an upgrade would silently serve stale output.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import uuid as uuid_module
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion import orchestrator, render
from app.ingestion.cdr import CDR_SCHEMA_VERSION, CanonicalDocument
from app.ingestion.converter import ConversionStatus, default_converter
from app.ingestion.extractors import AssetStatus, OcrStatus
from app.ingestion.pipeline import process_document
from app.ingestion.storage import get_store
from app.models.document import Document
from app.models.document_artifact import DocumentAsset, DocumentConversion, DocumentTable
from app.models.document_element import DocumentElement
from app.models.enums import (
    DocumentAssetStatus,
    DocumentConversionStatus,
    DocumentExtractionLevel,
    DocumentExtractionStatus,
    DocumentOcrStatus,
)
from app.services.audit import record_audit_log

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".md",
    ".html", ".htm", ".json", ".xml", ".epub",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff",
}

# Magic bytes for formats that have them. A file claiming .pdf whose bytes
# do not start with %PDF is rejected - extensions are uploader claims.
MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".epub": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
}

_STATUS_MAP = {
    ConversionStatus.SUCCEEDED: DocumentConversionStatus.SUCCEEDED,
    ConversionStatus.EMPTY: DocumentConversionStatus.EMPTY,
    ConversionStatus.UNSUPPORTED: DocumentConversionStatus.UNSUPPORTED,
    ConversionStatus.FAILED: DocumentConversionStatus.FAILED,
}
_ASSET_MAP = {
    AssetStatus.EXTRACTED: DocumentAssetStatus.EXTRACTED,
    AssetStatus.DETECTED_NOT_EXTRACTED: DocumentAssetStatus.DETECTED_NOT_EXTRACTED,
    AssetStatus.FAILED: DocumentAssetStatus.FAILED,
}
_OCR_MAP = {
    OcrStatus.NOT_ATTEMPTED: DocumentOcrStatus.NOT_ATTEMPTED,
    OcrStatus.SUCCEEDED: DocumentOcrStatus.SUCCEEDED,
    OcrStatus.NO_TEXT_FOUND: DocumentOcrStatus.NO_TEXT_FOUND,
    OcrStatus.UNAVAILABLE: DocumentOcrStatus.UNAVAILABLE,
    OcrStatus.FAILED: DocumentOcrStatus.FAILED,
}


def safe_extension(filename: str) -> str:
    """Extension of the BASENAME only.

    `Path(...).name` discards any directory component, so `../../x.pdf` and
    `/etc/x.pdf` both reduce to `x.pdf` here. The original string is kept
    for the audit record but never touches the filesystem."""
    return Path(Path(filename or "").name).suffix.lower()


def validate_upload(filename: str, data: bytes) -> None:
    """Runs BEFORE any parser sees the bytes."""
    extension = safe_extension(filename)
    if not extension:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File has no extension; cannot determine a converter.",
        )
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Extension {extension!r} is not accepted. Allowed: "
                f"{', '.join(sorted(ALLOWED_EXTENSIONS))}."
            ),
        )
    if len(data) == 0:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File is empty.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES} byte limit.",
        )

    expected = MAGIC_PREFIXES.get(extension)
    if expected and not any(data.startswith(prefix) for prefix in expected):
        # The extension is a claim; the bytes are evidence. When they
        # disagree, refuse rather than guess - handing a mislabelled file to
        # a parser is how parser exploits get reached.
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"File content does not match its {extension!r} extension. "
                "Refusing to process a mislabelled file."
            ),
        )


def find_reusable_conversion(
    db: Session, *, organization_id: UUID, source_hash: str,
    converter_name: str, converter_version: str,
) -> DocumentConversion | None:
    """Dedup key is hash + converter + VERSION (§22).

    Omitting the version would reuse an artifact produced by an older
    converter after an upgrade, silently serving stale Markdown that the
    current converter would not produce."""
    return db.execute(
        select(DocumentConversion).where(
            DocumentConversion.organization_id == organization_id,
            DocumentConversion.source_hash == source_hash,
            DocumentConversion.converter_name == converter_name,
            DocumentConversion.converter_version == converter_version,
            DocumentConversion.conversion_status == DocumentConversionStatus.SUCCEEDED,
        ).order_by(DocumentConversion.created_at.desc())
    ).scalars().first()


def persist_source_only(
    db: Session, *, organization_id: UUID, actor_user_id: UUID | None,
    source_id: UUID, filename: str, data: bytes, title: str | None = None,
    language: str = "en",
) -> tuple[Document, DocumentConversion]:
    """Phase 1 of ingestion: validate, retain the original, record a PENDING
    conversion. Runs inside the HTTP request because it is bounded — a hash
    and a file write — and because the original must be durable before the
    response is returned (P12-01).

    No conversion, no OCR, no table extraction happens here.
    """
    validate_upload(filename, data)
    source_hash = hashlib.sha256(data).hexdigest()

    stored = get_store().put(
        organization_id=organization_id, data=data, filename=filename
    )

    document = Document(
        organization_id=organization_id,
        source_id=source_id,
        title=(title or Path(Path(filename).name).stem)[:500],
        content=None,
        language=language,
        mime_type="application/octet-stream",
        file_size=len(data),
        content_hash=None,
        extraction_status=DocumentExtractionStatus.PENDING,
    )
    db.add(document)
    db.flush()

    converter = default_converter()
    conversion = DocumentConversion(
        organization_id=organization_id,
        document_id=document.id,
        original_filename=filename[:500],
        source_hash=source_hash,
        source_mime_type=None,
        source_size_bytes=len(data),
        storage_path=stored.storage_path,
        converter_name=converter.name,
        converter_version=converter.version,
        conversion_options={},
        conversion_status=DocumentConversionStatus.PENDING,
        extraction_level=DocumentExtractionLevel.NORMALIZE,
        warnings={"messages": []},
    )
    db.add(conversion)

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="document.source_persisted", resource_type="document",
        resource_id=document.id,
        new_value={"source_hash": source_hash, "bytes": len(data),
                   "deduplicated": stored.deduplicated},
    )
    db.commit()
    db.refresh(document)
    db.refresh(conversion)
    return document, conversion


def process_pending_conversion(
    db: Session, *, organization_id: UUID, document_id: UUID, conversion_id: UUID,
    enable_ocr: bool = True, ocr_languages: str = "eng", providers: list[str] | None = None,
) -> dict:
    """Phase 2: the expensive work, run by a Celery worker.

    Reads the RETAINED original rather than re-receiving bytes. That is the
    payoff from P12-01: the worker can reprocess at any time, including
    after a converter upgrade, because the source still exists.
    """
    conversion = db.execute(
        select(DocumentConversion).where(
            DocumentConversion.id == conversion_id,
            DocumentConversion.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if conversion is None:
        raise ValueError(f"conversion {conversion_id} not found for this organization")

    document = db.execute(
        select(Document).where(
            Document.id == document_id, Document.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if document is None:
        raise ValueError(f"document {document_id} not found for this organization")

    data = get_store().get(
        organization_id=organization_id, storage_path=conversion.storage_path
    )

    root = Path(tempfile.gettempdir()) / "aiol-quarantine"
    root.mkdir(parents=True, exist_ok=True)
    quarantine_dir = Path(tempfile.mkdtemp(dir=str(root)))
    extension = safe_extension(conversion.original_filename)
    quarantined = quarantine_dir / f"{uuid_module.uuid4().hex}{extension}"

    try:
        quarantined.write_bytes(data)
        conversion.processing_state = "processing"
        db.flush()
        result = process_document(
            quarantined, mime_type=None, converter=default_converter(),
            enable_ocr=enable_ocr, ocr_languages=ocr_languages,
        )
        # v4 (ADR-122): the canonical representation, with provider fallback. A crash here must not lose
        # the legacy result, so it is caught and recorded as a review reason, never raised.
        try:
            outcome = orchestrator.run(quarantined, options={"ocr_languages": ocr_languages},
                                       order=providers)
        except Exception as exc:  # noqa: BLE001
            outcome = orchestrator.ExtractionOutcome(
                review_reasons=[f"canonical_extraction_crashed:{type(exc).__name__}"])
        cdr = outcome.selected.document if outcome.selected else None
        if cdr is not None:
            _attach_embedded_image_ocr(cdr, result.extraction.images)

        # Markdown is rendered FROM the canonical representation (§7). Only when no provider could build
        # one does the legacy MarkItDown text stand in — and the extraction is then flagged for review.
        if cdr is not None and cdr.elements:
            content = render.to_markdown(cdr)
        else:
            content = result.canonical_markdown
            if content is not None:
                outcome.review_reasons.append("canonical_representation_unavailable")

        becomes_current = conversion.is_current or content is not None
        if becomes_current and not conversion.is_current:
            _supersede_current(db, organization_id=organization_id, document_id=document_id,
                               keep=conversion.id)
            conversion.is_current = True

        if conversion.is_current:
            document.content = content
            document.mime_type = "text/markdown" if content else "application/octet-stream"
            document.content_hash = hashlib.sha256(content.encode()).hexdigest() if content else None
            document.extraction_status = (
                DocumentExtractionStatus.EXTRACTED if content is not None
                else DocumentExtractionStatus.FAILED
            )

        _record_extraction(db, conversion=conversion, outcome=outcome, cdr=cdr, content=content)

        conversion.source_mime_type = result.conversion.source_mime_type
        conversion.conversion_status = _STATUS_MAP[result.conversion.status]
        conversion.conversion_error = result.conversion.error or None
        conversion.conversion_duration_seconds = result.conversion.duration_seconds
        conversion.conversion_options = result.conversion.conversion_options
        conversion.extraction_level = DocumentExtractionLevel(
            int(result.extraction.level_used.value)
        )
        conversion.output_hash = hashlib.sha256(content.encode()).hexdigest() if content else None
        conversion.output_size_bytes = len(content or "")
        conversion.page_count = result.extraction.page_count
        conversion.table_count = result.table_count
        conversion.image_count = result.image_count
        conversion.ocr_block_count = result.ocr_block_count
        conversion.ocr_engine = next(
            (i.ocr_engine for i in result.extraction.images if i.ocr_engine), None
        )
        conversion.ocr_version = next(
            (i.ocr_version for i in result.extraction.images if i.ocr_version), None
        )
        conversion.warnings = {"messages": result.warnings}
        conversion.completed_at = datetime.now(timezone.utc)

        # v4 §12: artifacts belong to the extraction that produced them. A retry of THIS conversion
        # replaces its own rows; a reprocess (a new conversion) adds rows beside the earlier ones, which
        # stay readable as that extraction's output. This used to delete every table and image of the
        # document on each run, so an earlier extraction could not be audited.
        db.query(DocumentTable).filter(
            DocumentTable.conversion_id == conversion_id,
            DocumentTable.organization_id == organization_id,
        ).delete(synchronize_session=False)
        db.query(DocumentAsset).filter(
            DocumentAsset.conversion_id == conversion_id,
            DocumentAsset.organization_id == organization_id,
        ).delete(synchronize_session=False)

        for position, table in enumerate(result.extraction.tables):
            if table.row_count == 0:
                continue
            db.add(DocumentTable(
                conversion_id=conversion_id,
                organization_id=organization_id, document_id=document_id,
                page_number=table.page_number, position=position,
                row_count=table.row_count, column_count=table.column_count,
                headers=table.headers, rows=table.rows, markdown=table.markdown,
                extraction_strategy=table.strategy,
                extraction_confidence=table.confidence,
            ))
        for image in result.extraction.images:
            db.add(DocumentAsset(
                conversion_id=conversion_id,
                organization_id=organization_id, document_id=document_id,
                asset_id=image.asset_id[:300], page_number=image.page_number,
                byte_size=image.byte_size, source_hash=image.source_hash or None,
                status=_ASSET_MAP[image.status], ocr_status=_OCR_MAP[image.ocr_status],
                ocr_text=image.ocr_text, ocr_engine=image.ocr_engine,
                ocr_version=image.ocr_version, error=image.error,
            ))

        db.commit()
        return {
            "document_id": str(document_id),
            "conversion_id": str(conversion_id),
            "conversion_status": conversion.conversion_status.value,
            "conversion_error": conversion.conversion_error,
            "extraction_level": int(conversion.extraction_level.value),
            "table_count": conversion.table_count,
            "image_count": conversion.image_count,
            "ocr_block_count": conversion.ocr_block_count,
            # v4: the canonical representation's own outcome, separate from MarkItDown's
            "layout_provider": conversion.layout_provider,
            "processing_state": conversion.processing_state,
            "needs_review": conversion.needs_review,
            "review_reasons": conversion.review_reasons,
            "is_current": conversion.is_current,
            "overall_confidence": conversion.overall_confidence,
        }
    finally:
        shutil.rmtree(quarantine_dir, ignore_errors=True)


# ---------------------------------------------------------------------- v4 canonical representation
def _attach_embedded_image_ocr(doc: CanonicalDocument, images: list) -> None:
    """The legacy pass OCRs embedded images; the layout provider locates them. Join the two by page and
    order of appearance, so a figure's recovered text lives on the figure it came from instead of being
    lost from the canonical representation."""
    figures = [e for e in doc.elements if e.element_type == "figure"
               and e.attributes.get("role") not in ("page_scan", "source_image")]
    by_page: dict = {}
    for img in images:
        by_page.setdefault(img.page_number, []).append(img)
    grouped: dict = {}
    for fig in figures:
        grouped.setdefault(fig.page, []).append(fig)
    for page, figs in grouped.items():
        legacy = by_page.get(page, [])
        figs = sorted(figs, key=lambda e: e.attributes.get("image_index", 0))
        for fig, img in zip(figs, legacy):
            fig.attributes["asset_id"] = img.asset_id
            fig.attributes["ocr_status"] = img.ocr_status.value
            if img.ocr_status == OcrStatus.SUCCEEDED and img.ocr_text:
                fig.attributes.update({"ocr_text": img.ocr_text, "ocr_engine": img.ocr_engine,
                                       "ocr_version": img.ocr_version})
        if len(legacy) != len(figs):
            doc.warnings.append(f"page {page}: {len(figs)} located figure(s) vs {len(legacy)} extracted "
                                "image(s); OCR text attached by order only where both exist")


def _supersede_current(db: Session, *, organization_id: UUID, document_id: UUID, keep: UUID) -> None:
    """Exactly one current extraction per document (a partial unique index enforces it). The previous one
    is marked superseded — never deleted — so its elements, tables and assets stay auditable."""
    now = datetime.now(timezone.utc)
    for old in db.execute(select(DocumentConversion).where(
            DocumentConversion.organization_id == organization_id,
            DocumentConversion.document_id == document_id,
            DocumentConversion.is_current.is_(True),
            DocumentConversion.id != keep)).scalars().all():
        old.is_current = False
        old.superseded_at = now
    db.flush()


def _record_extraction(db: Session, *, conversion: DocumentConversion, outcome,
                       cdr: CanonicalDocument | None, content: str | None) -> None:
    db.query(DocumentElement).filter(DocumentElement.conversion_id == conversion.id) \
        .delete(synchronize_session=False)
    conversion.candidates = [
        {"provider": c.provider, "provider_version": c.provider_version, "status": c.status,
         "reason": c.reason, "retryable": c.retryable, "overall_confidence": c.overall,
         "selected": c is outcome.selected}
        for c in outcome.candidates]
    reasons = list(dict.fromkeys(outcome.review_reasons))
    if cdr is not None:
        conf = cdr.confidence
        conversion.layout_provider = cdr.provider
        conversion.layout_provider_version = cdr.provider_version
        conversion.provider_config = cdr.config or {}
        conversion.cdr_schema_version = CDR_SCHEMA_VERSION
        conversion.document_class = cdr.document_class
        conversion.text_confidence = conf.text
        conversion.layout_confidence = conf.layout
        conversion.table_confidence = conf.table
        conversion.equation_confidence = conf.equation
        conversion.figure_confidence = conf.figure
        conversion.overall_confidence = conf.overall
        conversion.unprocessed_pages = cdr.unprocessed_pages
        conversion.provider_raw_output = cdr.raw_outputs.get("mmd")
        if cdr.page_count is not None:
            conversion.page_count = cdr.page_count
        for el in cdr.elements:
            db.add(DocumentElement(
                organization_id=conversion.organization_id, document_id=conversion.document_id,
                conversion_id=conversion.id, element_type=el.element_type, reading_order=el.reading_order,
                page=el.page, block_id=el.block_id[:120],
                parent_block_id=el.parent_block_id[:120] if el.parent_block_id else None,
                level=el.level, text=el.text, normalized_text=el.normalized_text, language=el.language,
                script=el.script, direction=el.direction, bbox=el.bbox, lines=el.lines or [],
                attributes=el.attributes or {}, confidence=el.confidence, method=el.method[:60]))
        if cdr.warnings:
            conversion.warnings = {"messages": [*(conversion.warnings or {}).get("messages", []), *cdr.warnings]}
    if content is None:
        state = "failed"
    elif cdr is not None and cdr.partially_processed:
        state = "partially_processed"
    elif reasons:
        state = "needs_review"
    else:
        state = "processed"
    conversion.processing_state = state
    conversion.review_reasons = reasons or (["extraction_failed"] if state == "failed" else [])
    conversion.needs_review = bool(conversion.review_reasons)
    db.flush()


def current_conversion(db: Session, *, organization_id: UUID, document_id: UUID) -> DocumentConversion | None:
    return db.execute(select(DocumentConversion).where(
        DocumentConversion.organization_id == organization_id,
        DocumentConversion.document_id == document_id,
        DocumentConversion.is_current.is_(True))).scalar_one_or_none()


def create_reprocess_conversion(db: Session, *, organization_id: UUID, document_id: UUID,
                                actor_user_id: UUID | None, trigger: str = "reprocess") -> DocumentConversion:
    """§38/§56 controlled reprocessing: a NEW extraction of the retained original, created non-current.
    It replaces the current extraction only if it succeeds; until then the document is unchanged."""
    latest = db.execute(select(DocumentConversion).where(
        DocumentConversion.organization_id == organization_id,
        DocumentConversion.document_id == document_id,
        DocumentConversion.storage_path.isnot(None)).order_by(DocumentConversion.created_at.desc())).scalars().first()
    if latest is None:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT,
                            detail="No retained original exists for this document; it cannot be reprocessed.")
    converter = default_converter()
    conversion = DocumentConversion(
        organization_id=organization_id, document_id=document_id,
        original_filename=latest.original_filename, source_hash=latest.source_hash,
        source_mime_type=latest.source_mime_type, source_size_bytes=latest.source_size_bytes,
        storage_path=latest.storage_path, converter_name=converter.name, converter_version=converter.version,
        conversion_options={}, conversion_status=DocumentConversionStatus.PENDING,
        extraction_level=DocumentExtractionLevel.NORMALIZE, warnings={"messages": []},
        is_current=False, processing_state="queued", trigger=trigger[:40])
    db.add(conversion)
    db.flush()
    record_audit_log(db, organization_id=organization_id, user_id=actor_user_id,
                     action="document.reprocess_requested", resource_type="document", resource_id=document_id,
                     new_value={"conversion_id": str(conversion.id), "trigger": trigger,
                                "previous_conversion_id": str(latest.id)})
    db.commit()
    db.refresh(conversion)
    return conversion
