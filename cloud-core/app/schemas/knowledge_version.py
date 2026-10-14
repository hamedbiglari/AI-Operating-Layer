"""Pydantic contracts for KnowledgeVersion."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_object_id: uuid.UUID
    version: int
    snapshot: dict
    change_summary: str | None
    created_by: uuid.UUID | None
    created_at: datetime
