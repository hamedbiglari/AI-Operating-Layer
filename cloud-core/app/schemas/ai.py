"""
Agent-facing API contracts (Phase 11).

Every response shape here is built around one requirement: an external AI
system consuming this API must not be able to mistake an absence of
knowledge for a negative fact, or an unverified claim for a verified one.

That is harder than it sounds, because the natural JSON shape destroys it.
`{"evidence_strength": 0.0}` reads as "bad". `{"claims": []}` reads as
"nothing to say". Neither conveys "we have not established this yet", which
is the true state most of the time and the one an honest agent should
report differently.

So every factual element carries an explicit STATE alongside any number,
and the top level carries a `coverage` block saying what the answer does
NOT cover. See ADR-057.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimEvidenceStrength, ClaimStatus, SignalState, TrustType


class AIClaim(BaseModel):
    """One claim, with its evidence standing made explicit.

    `evidence_strength` is Core's own aggregate (Phase 4). `is_disputed`
    surfaces CONFLICTING separately rather than folding it into a low
    strength, because "we found contradictory evidence" and "we found
    little evidence" are different things an agent should say differently.
    """

    claim_id: uuid.UUID
    predicate: str
    object_value: str | None
    object_entity_id: uuid.UUID | None
    status: ClaimStatus
    evidence_strength: ClaimEvidenceStrength
    is_disputed: bool
    verified_evidence_count: int


class AICoverage(BaseModel):
    """What this answer does NOT cover — returned always, never omitted.

    An agent that receives only positive facts will present them as the
    whole picture. This block is how the API says "here is the edge of what
    we know", which is the difference between a useful source and a
    confident-sounding one.
    """

    has_knowledge_object: bool
    claim_count: int
    approved_claim_count: int
    disputed_claim_count: int
    unverified_claim_count: int
    evidence_state: SignalState
    caveats: list[str] = Field(default_factory=list)


class AIKnowledgeResponse(BaseModel):
    knowledge_object_id: uuid.UUID
    canonical_name: str
    object_type: str
    claims: list[AIClaim]
    coverage: AICoverage
    # Machine-readable provenance: which Core this came from, and when.
    # An agent caching this needs to know how stale it may be.
    as_of: datetime


class AITrustRecord(BaseModel):
    """VERIFIED trust records only — see the endpoint docstring."""

    trust_type: TrustType
    claim: str
    verified_at: datetime | None


class AITrustResponse(BaseModel):
    product_id: uuid.UUID
    product_name: str
    verified_trust: list[AITrustRecord]
    coverage: AICoverage
    as_of: datetime


class AIAskRequest(BaseModel):
    """Minimal input, matching section 32's privacy stance: a topic and an
    intent, never a conversation transcript."""

    topic: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=255)
    knowledge_object_id: uuid.UUID | None = None
    purchase_intent: str = Field(default="researching", max_length=32)
    limit: int = Field(default=5, ge=1, le=20)


class AIAnswerProduct(BaseModel):
    product_id: uuid.UUID
    name: str
    evidence_state: SignalState
    trust_state: SignalState
    caveats: list[str]
    # Deliberately NOT called "score" or "rating". Section 33: the internal
    # score is a decision signal, not a rating, and must never be presented
    # as one to an external consumer. The rank position is all an agent
    # needs, and it cannot be misquoted as "9.2/10".
    rank: int
    # Where to buy: the merchant's own product page (master spec §1 "routing
    # users to the original merchant website", §35 AI -> product card ->
    # merchant website). Only merchant-asserted data is used: the chosen
    # offer's URL, else the permalink the merchant's own adapter published
    # for this product. NULL when neither exists — never guessed.
    merchant_url: str | None = None


class AIAnswerResponse(BaseModel):
    """`answerable` is the field that matters.

    False with an empty product list is a complete, successful answer —
    it means the system declined, and an agent should say so rather than
    improvising. Section 34 forbids pushing products when intent does not
    justify it; this is that rule made consumable.
    """

    answerable: bool
    reason: str
    products: list[AIAnswerProduct] = Field(default_factory=list)
    coverage: AICoverage
    as_of: datetime


class AICapabilityDescriptor(BaseModel):
    """Self-describing capability manifest.

    Section 63 fixes MCP as a *future/secondary* interface, so Phase 11
    does not build an MCP server. It builds the thing an MCP server would
    wrap: a machine-readable description of what this API can answer, what
    it refuses to answer, and what its honesty guarantees are. See ADR-058.
    """

    api_version: str
    interface: str
    capabilities: list[dict]
    guarantees: list[str]
    refusals: list[str]
