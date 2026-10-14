"""Pydantic contracts for Entity."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_object_id: uuid.UUID
    entity_type: str
    canonical_name: str
    aliases: list | None
    external_ids: dict | None
    language: str
    created_at: datetime
    updated_at: datetime


class EntityCreate(BaseModel):
    knowledge_object_id: uuid.UUID
    entity_type: str = Field(min_length=1, max_length=100)
    canonical_name: str = Field(min_length=1, max_length=500)
    aliases: list[str] | None = None
    external_ids: dict[str, str] | None = None
    language: str = Field(default="en", max_length=10)


class EntityUpdate(BaseModel):
    entity_type: str | None = Field(default=None, min_length=1, max_length=100)
    canonical_name: str | None = Field(default=None, min_length=1, max_length=500)
    aliases: list[str] | None = None
    external_ids: dict[str, str] | None = None
    language: str | None = Field(default=None, max_length=10)
