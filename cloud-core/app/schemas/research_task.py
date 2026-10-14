"""Pydantic contracts for ResearchTask."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResearchTaskStatus


class ResearchTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    research_project_id: uuid.UUID
    task_type: str
    query: str
    status: ResearchTaskStatus
    result: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchTaskCreate(BaseModel):
    research_project_id: uuid.UUID
    task_type: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1)


class ResearchTaskUpdate(BaseModel):
    """Plain field edits only, and only while the task is still PENDING
    (research_task_service.update_research_task enforces this) — once a
    task is QUEUED or beyond, its query/task_type are part of its
    execution record and must not silently change out from under it."""

    task_type: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(default=None, min_length=1)
