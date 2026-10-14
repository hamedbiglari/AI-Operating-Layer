"""Pydantic contracts for QueryGroup and its membership + the
read-only Knowledge Need assessment."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IntentType, QueryPriority


class QueryGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    primary_intent: IntentType
    target_entity_id: uuid.UUID | None
    priority: QueryPriority
    created_at: datetime
    updated_at: datetime


class QueryGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    primary_intent: IntentType
    target_entity_id: uuid.UUID | None = None
    priority: QueryPriority = QueryPriority.MEDIUM


class QueryGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    priority: QueryPriority | None = None


class QueryGroupMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_group_id: uuid.UUID
    query_id: uuid.UUID
    created_at: datetime


class QueryGroupMembershipCreate(BaseModel):
    query_id: uuid.UUID


class KnowledgeNeedAssessment(BaseModel):
    """A computed judgment, not a persisted row — see
    query_group_service.py's module docstring for why Knowledge Need is
    deliberately NOT its own database table. If `is_gap_worthy` is
    True, the caller decides whether to act on it via the EXISTING
    `POST /knowledge-gaps` endpoint (Phase 2) — this assessment never
    creates a gap itself."""

    query_group_id: uuid.UUID
    has_target_entity: bool
    knowledge_object_id: uuid.UUID | None
    claim_count: int
    adequately_evidenced_claim_count: int
    is_gap_worthy: bool
    reason: str
