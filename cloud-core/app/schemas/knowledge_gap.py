"""Pydantic contracts for KnowledgeGap."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GapPriority, GapRecommendedAction, GapStatus, GapType


class KnowledgeGapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_object_id: uuid.UUID
    gap_type: GapType
    description: str
    priority: GapPriority
    status: GapStatus
    recommended_action: GapRecommendedAction | None
    created_at: datetime
    updated_at: datetime


class KnowledgeGapCreate(BaseModel):
    knowledge_object_id: uuid.UUID
    gap_type: GapType
    description: str = Field(min_length=1)
    priority: GapPriority = GapPriority.MEDIUM
    recommended_action: GapRecommendedAction | None = None


class KnowledgeGapUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    priority: GapPriority | None = None
    status: GapStatus | None = None
    recommended_action: GapRecommendedAction | None = None
