"""Pydantic contracts for Source."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SourceAccessStatus, SourceRightsStatus


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_type: str
    title: str
    author: str | None
    url: str | None
    doi: str | None
    pmid: str | None
    isbn: str | None
    publisher: str | None
    publication_date: date | None
    access_status: SourceAccessStatus
    rights_status: SourceRightsStatus
    reliability_score: float | None
    # The ORM attribute is `metadata_` (plain `metadata` collides with
    # SQLAlchemy's declarative base attribute of the same name) — this
    # alias pair reads app.models.source.Source.metadata_ and serializes
    # it back to the API-facing name `metadata`.
    metadata_value: dict = Field(validation_alias="metadata_", serialization_alias="metadata")
    # pilot-ready access model — what was found vs what the system actually holds
    existence_status: str = "unconfirmed"
    content_access: str = "unknown"
    full_text_accessed: bool = False
    accessed_parts: list | None = None
    acquisition_paths: dict | None = None
    review_status: str = "not_reviewed"
    full_text_origin: str | None = None
    access_blocked_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    doi: str | None = Field(default=None, max_length=255)
    pmid: str | None = Field(default=None, max_length=50)
    isbn: str | None = Field(default=None, max_length=50)
    publisher: str | None = Field(default=None, max_length=255)
    publication_date: date | None = None
    access_status: SourceAccessStatus = SourceAccessStatus.UNKNOWN
    rights_status: SourceRightsStatus = SourceRightsStatus.UNKNOWN
    reliability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    doi: str | None = Field(default=None, max_length=255)
    pmid: str | None = Field(default=None, max_length=50)
    isbn: str | None = Field(default=None, max_length=50)
    publisher: str | None = Field(default=None, max_length=255)
    publication_date: date | None = None
    access_status: SourceAccessStatus | None = None
    rights_status: SourceRightsStatus | None = None
    reliability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict | None = None
