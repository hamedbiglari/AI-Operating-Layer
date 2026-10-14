"""Pydantic contracts for Claim."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ClaimEvidenceStrength, ClaimStatus


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_object_id: uuid.UUID
    subject_entity_id: uuid.UUID
    predicate: str
    object_entity_id: uuid.UUID | None
    object_value: str | None
    section_key: str | None = None
    claim_type: str | None
    evidence_strength: ClaimEvidenceStrength
    confidence: float | None
    status: ClaimStatus
    source_generated: bool
    human_reviewed: bool
    created_at: datetime
    updated_at: datetime


class ClaimCreate(BaseModel):
    knowledge_object_id: uuid.UUID
    subject_entity_id: uuid.UUID
    predicate: str = Field(min_length=1, max_length=200)
    object_entity_id: uuid.UUID | None = None
    object_value: str | None = None
    claim_type: str | None = Field(default=None, max_length=100)
    # ADR-114: the knowledge section this claim belongs to, so a matrix cell reads real claims
    section_key: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_exactly_one_object_representation(self) -> "ClaimCreate":
        has_entity = self.object_entity_id is not None
        has_value = bool(self.object_value and self.object_value.strip())
        if has_entity == has_value:  # both provided, or neither provided
            raise ValueError(
                "Exactly one of object_entity_id or object_value must be provided (not both, not neither)"
            )
        return self


class ClaimUpdate(BaseModel):
    """General field edits. Review-lifecycle transitions (approve/reject)
    go through the dedicated /claims/{id}/review action instead, so a
    plain field edit can never silently flip status.

    PATCH semantics for object_entity_id/object_value (fixed after Phase
    2 review — previously "not provided" and "explicitly cleared" were
    indistinguishable):

    - Omit a field entirely from the JSON body -> left unchanged.
    - Send it explicitly as `null` -> that representation is cleared,
      which is only valid if the OTHER representation is being set (in
      the same request) or is already set on the claim.
    - Send a non-null value -> that representation is set, and the
      other representation is automatically cleared (switching from a
      literal value to an entity reference, or vice versa, in one call).
    - Sending both object_entity_id and object_value as non-null in the
      same request is always rejected — the XOR invariant is enforced
      on every write path, not just at creation.

    The service layer (`app/services/claim_service.py::update_claim`)
    is driven by explicit `*_provided` booleans that the API layer
    (`app/api/v1/claims.py`) derives from `payload.model_fields_set` —
    the set of field names actually present in the request body. The
    default value alone can't distinguish "omitted" from "sent as null".
    """

    predicate: str | None = Field(default=None, min_length=1, max_length=200)
    object_entity_id: uuid.UUID | None = None
    object_value: str | None = None
    claim_type: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ClaimReviewRequest(BaseModel):
    status: ClaimStatus = Field(description="Must be one of the reviewed terminal/interim states.")
    evidence_strength: ClaimEvidenceStrength | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def status_must_be_a_review_outcome(self) -> "ClaimReviewRequest":
        allowed = {
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.APPROVED,
            ClaimStatus.REJECTED,
            ClaimStatus.DISPUTED,
            ClaimStatus.DEPRECATED,
        }
        if self.status not in allowed:
            raise ValueError(f"status must be one of: {', '.join(s.value for s in allowed)}")
        return self
