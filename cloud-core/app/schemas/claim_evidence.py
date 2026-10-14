"""Pydantic contracts for ClaimEvidence (the Claim<->Evidence link)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvidenceRelation


class ClaimEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    relation: EvidenceRelation
    weight: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ClaimEvidenceCreate(BaseModel):
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS
    weight: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = Field(default=None, max_length=2000)


class ClaimEvidenceUpdate(BaseModel):
    relation: EvidenceRelation | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = Field(default=None, max_length=2000)
