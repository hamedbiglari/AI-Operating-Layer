"""Pydantic contracts for KnowledgeObject."""

import uuid
from datetime import datetime

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import KnowledgeObjectStatus


class KnowledgeObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    canonical_name: str
    slug: str
    object_type: str
    category_id: UUID | None = None
    description: str | None
    status: KnowledgeObjectStatus
    language: str
    confidence: float | None
    public_visibility: bool
    ai_visibility: bool
    version: int
    created_at: datetime
    updated_at: datetime


class KnowledgeObjectCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    slug: str | None = Field(default=None, max_length=500)
    object_type: str = Field(min_length=1, max_length=100)
    description: str | None = None
    language: str = Field(default="en", max_length=10)
    confidence: float | None = Field(default=None, ge=0, le=1)


class KnowledgeObjectUpdate(BaseModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=500)
    # ADR-114: assigning a topic to a Category gives it that category's section schema.
    category_id: UUID | None = None
    description: str | None = None
    status: KnowledgeObjectStatus | None = None
    language: str | None = Field(default=None, max_length=10)
    confidence: float | None = Field(default=None, ge=0, le=1)
    public_visibility: bool | None = None
    ai_visibility: bool | None = None
    change_summary: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional human-readable note stored on the resulting KnowledgeVersion snapshot.",
    )
