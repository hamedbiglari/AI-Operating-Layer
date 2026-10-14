"""Pydantic contracts for ResearchProject."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ResearchMode, ResearchProjectStatus


class ResearchProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    objective: str
    mode: ResearchMode
    knowledge_gap_id: uuid.UUID | None
    status: ResearchProjectStatus
    created_at: datetime
    updated_at: datetime


class ResearchProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1)
    mode: ResearchMode
    knowledge_gap_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def gap_driven_requires_gap(self) -> "ResearchProjectCreate":
        if self.mode == ResearchMode.GAP_DRIVEN and self.knowledge_gap_id is None:
            raise ValueError("knowledge_gap_id is required when mode is 'gap_driven'")
        return self


class ResearchProjectUpdate(BaseModel):
    """Plain field edits only — status transitions go through the
    dedicated /research/projects/{id}/transition action instead (same
    split as Claim/Evidence's review endpoints: a plain edit must never
    silently change lifecycle state)."""

    name: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = Field(default=None, min_length=1)


class ResearchProjectTransitionRequest(BaseModel):
    status: ResearchProjectStatus
