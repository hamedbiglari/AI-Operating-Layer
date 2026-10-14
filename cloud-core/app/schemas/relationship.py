"""Pydantic contracts for Relationship."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GraphNodeType, RelationshipStatus


class RelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subject_type: GraphNodeType
    subject_id: uuid.UUID
    predicate: str
    object_type: GraphNodeType
    object_id: uuid.UUID
    confidence: float | None
    source_id: uuid.UUID | None
    status: RelationshipStatus
    created_at: datetime
    updated_at: datetime


class RelationshipCreate(BaseModel):
    subject_type: GraphNodeType
    subject_id: uuid.UUID
    predicate: str = Field(min_length=1, max_length=200)
    object_type: GraphNodeType
    object_id: uuid.UUID
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_id: uuid.UUID | None = None


class RelationshipUpdate(BaseModel):
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: RelationshipStatus | None = None
