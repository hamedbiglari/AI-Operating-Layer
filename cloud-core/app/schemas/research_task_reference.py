"""Pydantic contracts for ResearchTaskReference — a task's provenance
trail. Read-only via the API: entries are written internally by
research_task_service.execute_research_task from a provider's reported
ResearchReference list, never posted directly by a client."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ResearchReferenceRole, ResearchReferenceType


class ResearchTaskReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    research_task_id: uuid.UUID
    reference_type: ResearchReferenceType
    reference_id: uuid.UUID
    role: ResearchReferenceRole
    created_at: datetime
