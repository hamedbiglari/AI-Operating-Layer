"""Pydantic contracts for Evidence."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvidenceDirectness, EvidenceStatus, EvidenceStrength


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_id: uuid.UUID
    document_id: uuid.UUID | None
    document_chunk_id: uuid.UUID | None
    study_type: str | None
    directness: EvidenceDirectness
    evidence_strength: EvidenceStrength
    status: EvidenceStatus
    summary: str
    sample_size: int | None
    population: str | None
    source_generated: bool
    human_reviewed: bool
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(BaseModel):
    source_id: uuid.UUID
    document_id: uuid.UUID | None = None
    document_chunk_id: uuid.UUID | None = None
    study_type: str | None = Field(default=None, max_length=100)
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT
    evidence_strength: EvidenceStrength = EvidenceStrength.VERY_LOW
    summary: str = Field(min_length=1)
    sample_size: int | None = Field(default=None, ge=0)
    population: str | None = Field(default=None, max_length=500)


class EvidenceUpdate(BaseModel):
    """General field edits. Review-lifecycle transitions (verify/reject)
    go through the dedicated /evidence/{id}/review action instead —
    mirrors ClaimUpdate/ClaimReviewRequest's split for the same reason:
    a plain field edit must never silently flip review status."""

    document_id: uuid.UUID | None = None
    document_chunk_id: uuid.UUID | None = None
    study_type: str | None = Field(default=None, max_length=100)
    directness: EvidenceDirectness | None = None
    evidence_strength: EvidenceStrength | None = None
    summary: str | None = Field(default=None, min_length=1)
    sample_size: int | None = Field(default=None, ge=0)
    population: str | None = Field(default=None, max_length=500)


class EvidenceReviewRequest(BaseModel):
    status: EvidenceStatus = Field(description="Must be one of the reviewed terminal/interim states.")
    evidence_strength: EvidenceStrength | None = None
    note: str | None = Field(default=None, max_length=2000)
