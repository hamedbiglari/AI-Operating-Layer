"""Pydantic contracts for Query and QueryProvenance."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QueryPriority, QuerySource, QueryStatus


class QueryProvenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_id: uuid.UUID
    source: QuerySource
    raw_query: str
    metadata_: dict = Field(alias="metadata")
    created_at: datetime


class QueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    query: str
    normalized_query: str
    language: str
    country: str | None
    source: QuerySource
    search_volume: int | None
    commercial_value: float | None
    priority: QueryPriority
    status: QueryStatus
    discovered_at: datetime
    created_at: datetime
    updated_at: datetime


class QueryImportRow(BaseModel):
    """One row of an import — a CSV row, an Excel row (future), or a
    single manual entry (manual creation reuses this same shape with
    source=MANUAL, per the approved design decision to route single-
    query creation through the same import path rather than adding a
    bare `POST /queries` beyond section 50's literal endpoint list)."""

    query: str = Field(min_length=1, max_length=1000)
    language: str = Field(default="en", max_length=10)
    country: str | None = Field(default=None, max_length=10)
    search_volume: int | None = Field(default=None, ge=0)
    commercial_value: float | None = Field(default=None, ge=0)
    priority: QueryPriority = QueryPriority.MEDIUM
    discovered_at: datetime | None = None


class QueryImportRequest(BaseModel):
    """Body for manual/programmatic (non-file) import — a small batch
    of rows, all sharing one `source`. CSV file uploads use the same
    underlying service function via a multipart endpoint instead of
    this JSON body; see app/api/v1/queries.py."""

    source: QuerySource
    rows: list[QueryImportRow] = Field(min_length=1, max_length=5000)


class QueryImportResultItem(BaseModel):
    query_id: uuid.UUID
    query: str
    created: bool  # True if a new Query row was created, False if an existing one was matched and a provenance row was appended


class QueryImportResult(BaseModel):
    created_count: int
    matched_count: int
    items: list[QueryImportResultItem]


class QueryUpdate(BaseModel):
    """Plain field edits. Does not touch `status` — CLASSIFIED is set
    automatically when an Intent is created
    (app/services/intent_service.py), and ARCHIVED is a dedicated
    action (`POST /queries/{id}/archive`), never a PATCH target, same
    review/status-split principle used throughout this codebase."""

    search_volume: int | None = Field(default=None, ge=0)
    commercial_value: float | None = Field(default=None, ge=0)
    priority: QueryPriority | None = None
