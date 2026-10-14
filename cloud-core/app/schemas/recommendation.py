"""Pydantic contracts for CustomerContext and Recommendation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ConsentStatus,
    ContextSource,
    ContextType,
    IntentType,
    NeedLevel,
    PriceSensitivity,
    PurchaseIntent,
    RecommendationStatus,
    ResponseMode,
    SignalState,
)


# --- Customer Context ------------------------------------------------------


class CustomerContextRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: str | None
    session_id: str | None
    context_type: ContextType
    intent: IntentType | None
    topic: str | None
    purchase_intent: PurchaseIntent
    evidence_need: NeedLevel
    trust_need: NeedLevel
    price_sensitivity: PriceSensitivity
    product_interest: str | None
    preferences: dict
    consent_status: ConsentStatus
    source: ContextSource
    created_at: datetime
    updated_at: datetime


class CustomerContextCreate(BaseModel):
    """Every field is optional except `source`. An empty context is a
    valid, fully anonymous one — the engine must never require an
    identity to answer a question (master spec section 32's
    privacy-safe default)."""

    customer_id: str | None = Field(default=None, max_length=255)
    session_id: str | None = Field(default=None, max_length=255)
    context_type: ContextType = ContextType.ANONYMOUS
    intent: IntentType | None = None
    topic: str | None = Field(default=None, max_length=500)
    purchase_intent: PurchaseIntent = PurchaseIntent.NONE
    evidence_need: NeedLevel = NeedLevel.NORMAL
    trust_need: NeedLevel = NeedLevel.NORMAL
    price_sensitivity: PriceSensitivity = PriceSensitivity.UNKNOWN
    product_interest: str | None = Field(default=None, max_length=500)
    preferences: dict = Field(default_factory=dict)
    consent_status: ConsentStatus = ConsentStatus.NOT_REQUIRED
    source: ContextSource = ContextSource.API


class CustomerContextUpdate(BaseModel):
    """Explicit-null semantics, same as Phase 7 (ADR-026): an absent key
    leaves the field alone, an explicit null clears it."""

    intent: IntentType | None = None
    topic: str | None = Field(default=None, max_length=500)
    purchase_intent: PurchaseIntent | None = None
    evidence_need: NeedLevel | None = None
    trust_need: NeedLevel | None = None
    price_sensitivity: PriceSensitivity | None = None
    product_interest: str | None = Field(default=None, max_length=500)
    preferences: dict | None = None
    consent_status: ConsentStatus | None = None


# --- Recommendation ---------------------------------------------------------


class SignalExplanation(BaseModel):
    """A score is meaningless without its state and its reason. All
    three always travel together — see Recommendation's model
    docstring."""

    score: float
    state: SignalState
    detail: str


class RecommendationReason(BaseModel):
    """The structured shape stored in `Recommendation.reason`.

    Deliberately machine-readable rather than prose: a future AI agent
    or dashboard must be able to answer "why this product, what would
    change the answer" without parsing English."""

    primary_reason: str
    relevance: SignalExplanation
    evidence: SignalExplanation
    trust: SignalExplanation
    availability: SignalExplanation
    caveats: list[str] = Field(default_factory=list)
    rejected_by_gate: str | None = None
    policy_version: str


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_context_id: uuid.UUID | None
    product_id: uuid.UUID
    offer_id: uuid.UUID | None
    query_id: uuid.UUID | None
    knowledge_object_id: uuid.UUID | None
    response_mode: ResponseMode
    relevance_score: float
    evidence_score: float
    trust_score: float
    availability_score: float
    final_score: float
    evidence_state: SignalState
    trust_state: SignalState
    reason: dict
    status: RecommendationStatus
    policy_version: str
    created_at: datetime


class RecommendationRequest(BaseModel):
    """Minimal context in, per the Phase 8 brief: a caller supplies a
    topic/intent/constraints, never raw conversation history.

    `persist=False` lets a caller evaluate without writing rows —
    useful for previewing, and it keeps the audit trail free of
    speculative evaluations."""

    response_mode: ResponseMode
    customer_context_id: uuid.UUID | None = None
    query_id: uuid.UUID | None = None
    knowledge_object_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    product_ids: list[uuid.UUID] | None = None
    limit: int = Field(default=10, ge=1, le=50)
    persist: bool = True


class RejectedCandidate(BaseModel):
    """Why a product did NOT make it. The Phase 8 brief requires the
    system to answer "why not another product?", which is impossible if
    rejections are silently dropped."""

    product_id: uuid.UUID
    product_name: str
    failed_gate: str
    detail: str


class RecommendationResponse(BaseModel):
    """`status` at the top level is the answer to the REQUEST;
    each item carries its own per-product status.

    NO_RECOMMENDATION with an empty `recommendations` list is a
    legitimate, fully-successful outcome — not an error."""

    status: RecommendationStatus
    response_mode: ResponseMode
    policy_version: str
    explanation: str
    recommendations: list[RecommendationRead] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
