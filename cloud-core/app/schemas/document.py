"""Pydantic contracts for Document."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    SyncJobStatus,
    SyncJobType,
    DocumentAssetStatus,
    DocumentConversionStatus,
    DocumentExtractionStatus,
    DocumentOcrStatus,
)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_id: uuid.UUID
    title: str
    content: str | None
    language: str
    content_hash: str | None
    version: int
    mime_type: str
    file_size: int | None
    storage_path: str | None
    extraction_status: DocumentExtractionStatus
    created_at: datetime
    updated_at: datetime


class CurrentConversionRead(BaseModel):
    id: uuid.UUID
    status: DocumentConversionStatus
    needs_review: bool


class DocumentWithConversion(BaseModel):
    """A row of GET /sources/{id}/documents: the document without its text
    (the list never shows it; GET /documents/{id}/markdown serves it) and
    with its current conversion, None when it has none."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_id: uuid.UUID
    title: str
    language: str
    content_hash: str | None
    version: int
    mime_type: str
    file_size: int | None
    storage_path: str | None
    extraction_status: DocumentExtractionStatus
    created_at: datetime
    updated_at: datetime
    current_conversion: CurrentConversionRead | None = None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=2_000_000)
    language: str = Field(default="en", max_length=10)
    mime_type: str = Field(default="text/plain", max_length=100)
    storage_path: str | None = Field(default=None, max_length=1000)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=2_000_000)
    language: str | None = Field(default=None, max_length=10)
    extraction_status: DocumentExtractionStatus | None = None


# --- Phase 3 completion: Document Intelligence contracts (ADR-065) --------


class DocumentIngestionResponse(BaseModel):
    """Reports what the pipeline ACTUALLY did, not merely that it ran.

    `extraction_level` and the counts are the honest part: a caller can see
    that a figure was found and whether anything was read from it. A bare
    "success" would hide the difference between a clean extraction and one
    that silently lost a chart."""

    # Null for a URL job: nothing has been fetched yet, so no document
    # exists. Absence here means "not yet", never "failed".
    document_id: uuid.UUID | None = None
    conversion_id: uuid.UUID | None = None
    conversion_status: DocumentConversionStatus
    extraction_level: int
    converter_name: str
    converter_version: str
    source_hash: str
    page_count: int | None
    table_count: int
    image_count: int
    ocr_block_count: int
    ocr_engine: str | None
    # NULL unless a vision model interpreted an image. Level 4 is not built,
    # so this is always NULL today — the field exists so model-derived
    # content is distinguishable the moment it appears.
    vision_model: str | None
    warnings: list[str]
    conversion_error: str | None


class DocumentTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int | None
    position: int
    row_count: int
    column_count: int
    headers: list
    rows: list
    markdown: str
    extraction_strategy: str
    extraction_confidence: float


class DocumentAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: str
    page_number: int | None
    byte_size: int
    source_hash: str | None
    status: DocumentAssetStatus
    ocr_status: DocumentOcrStatus
    ocr_text: str | None
    ocr_engine: str | None
    ocr_version: str | None
    vision_model: str | None
    vision_description: str | None
    error: str | None


class DocumentArtifactsResponse(BaseModel):
    document_id: uuid.UUID
    tables: list[DocumentTableRead]
    assets: list[DocumentAssetRead]


class DocumentIngestionJobStatus(BaseModel):
    """`status` is the JOB outcome; `conversion_status` is the DOCUMENT
    outcome. A job can succeed while reporting that the file could not be
    converted — those are different facts and are surfaced separately."""

    job_id: uuid.UUID
    status: SyncJobStatus
    conversion_status: DocumentConversionStatus | None
    attempts: int
    document_id: uuid.UUID | None
    conversion_id: uuid.UUID | None
    # What the run actually produced. Surfaced here so a caller polling a
    # job learns the outcome without a second request, and so "succeeded
    # with 0 tables" is visible rather than implied.
    extraction_level: int | None = None
    table_count: int | None = None
    image_count: int | None = None
    ocr_block_count: int | None = None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    result: dict | None


class UrlIngestionRequest(BaseModel):
    """URL ingestion input. `url` is a plain string validated by the SSRF
    layer rather than Pydantic's `AnyHttpUrl`: Pydantic checks shape, and
    shape is not the threat here — `http://169.254.169.254/` is a perfectly
    well-formed URL."""

    source_id: uuid.UUID
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=500)
    language: str = Field(default="en", max_length=10)
    idempotency_key: str | None = Field(default=None, max_length=200)


class DocumentIngestionAccepted(BaseModel):
    """THE single 202 contract for ingestion (P12-02).

    Consolidated from three near-identical drafts that accumulated during
    implementation — duplicate abstraction is the same fault P12-17 targets,
    so they were removed rather than left side by side.

    `storage_path_recorded` is explicit rather than implied: it tells the
    caller the original bytes are durable, which is the difference between
    "accepted" and "queued and hopefully still there".

    `job_created=False` means an identical upload was already queued; the
    caller gets that job rather than a second ingestion (P12-04).
    """

    job_id: uuid.UUID
    status: SyncJobStatus
    # Which kind of job was created. Explicit so a caller polling
    # /sync-jobs knows what it is looking at without inferring from the URL.
    job_type: SyncJobType
    job_created: bool
    source_hash: str
    storage_path_recorded: bool
    created_at: datetime
    status_url: str
    # Returned immediately: the document and conversion rows exist before
    # the 202, so a caller can reference them while the pipeline runs.
    # Null for a URL job: nothing has been fetched yet, so no document
    # exists. Absence here means "not yet", never "failed".
    document_id: uuid.UUID | None = None
    conversion_id: uuid.UUID | None = None
