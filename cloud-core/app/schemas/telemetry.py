"""
Phase 13 API schemas.

Two rules visible throughout:

1. **Nullable stays nullable on the wire.** `dwell_ms`, `result_count`,
   every geo field and `mean_dwell_ms` are `| None`, and the client is
   expected to render *Not available*. A response model that defaulted
   them to 0 would put the lie in the contract itself, where no UI fix
   could reach it.
2. **The ingest schema never carries `organization_id`.** Same rule as
   Phase 9 (ADR-036): the tenant comes from the credential. There is no
   field here a caller could use to write into someone else's tenant.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AccessDecision,
    AccessPurpose,
    AccessTier,
    ActorConfidence,
    ActorType,
    AgentRegistrationOrigin,
    GeoResolutionMethod,
    SearchDemandSource,
)

# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class PageViewIngest(BaseModel):
    """One observed page view, as reported by an adapter."""

    # Client-minted, and the entire basis of safe retries.
    event_key: str = Field(min_length=8, max_length=64)
    occurred_at: datetime
    path: str = Field(min_length=1, max_length=512)

    site_id: uuid.UUID | None = None
    content_type: str | None = Field(default=None, max_length=80)
    content_title: str | None = Field(default=None, max_length=500)
    status_code: int | None = Field(default=None, ge=100, le=599)

    user_agent: str | None = Field(default=None, max_length=400)
    referrer_host: str | None = Field(default=None, max_length=255)
    purpose: AccessPurpose = AccessPurpose.UNKNOWN
    confidence: ActorConfidence = ActorConfidence.UNKNOWN

    # Personal data. Accepted because the owner has decided it is required
    # (ADR-079); retained for a bounded window and truncated on write.
    ip_address: str | None = Field(default=None, max_length=64)

    geo_method: GeoResolutionMethod | None = None
    geo_country: str | None = Field(default=None, min_length=2, max_length=2)
    geo_region: str | None = Field(default=None, max_length=80)
    geo_city: str | None = Field(default=None, max_length=120)
    geo_latitude: float | None = Field(default=None, ge=-90, le=90)
    geo_longitude: float | None = Field(default=None, ge=-180, le=180)
    geo_timezone: str | None = Field(default=None, max_length=64)

    # NULL = not reported. Never coerced to 0 - see module docstring.
    dwell_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    dwell_is_complete: bool = False

    @field_validator("path")
    @classmethod
    def strip_query_string(cls, v: str) -> str:
        """Defence in depth. The adapter already strips it; a query string
        routinely carries personal data, and one careless caller should not
        be able to put it in the analytics store."""
        return v.split("?", 1)[0].split("#", 1)[0]

    @field_validator("geo_country")
    @classmethod
    def upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PageViewBatch(BaseModel):
    # 500 is a deliberate ceiling: large enough that a busy site batches
    # efficiently, small enough that one rejected batch is a small loss.
    events: list[PageViewIngest] = Field(min_length=1, max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    agents_discovered: int
    # Populated on partial failure. An empty list and a missing field are
    # different; this is always present.
    errors: list[str] = Field(default_factory=list)


class SearchDemandIngest(BaseModel):
    event_key: str = Field(min_length=8, max_length=64)
    occurred_at: datetime
    search_text: str = Field(min_length=1, max_length=1000)
    demand_source: SearchDemandSource = SearchDemandSource.ONSITE_SEARCH
    site_id: uuid.UUID | None = None
    user_agent: str | None = Field(default=None, max_length=400)
    result_count: int | None = Field(default=None, ge=0)
    path: str | None = Field(default=None, max_length=512)
    language: str = Field(default="fa", max_length=10)
    geo_country: str | None = Field(default=None, min_length=2, max_length=2)


class SearchDemandBatch(BaseModel):
    events: list[SearchDemandIngest] = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


class AiAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    signature: str
    display_name: str
    vendor: str | None
    actor_type: ActorType
    declared_purpose: AccessPurpose
    confidence: ActorConfidence
    origin: AgentRegistrationOrigin
    # Rendered beside the confidence badge. Never omitted by the UI.
    verification_note: str | None
    sample_user_agent: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    observation_count: int
    created_at: datetime
    updated_at: datetime


class AiAgentRename(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)


class PageViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID | None
    path: str
    content_type: str | None
    content_title: str | None
    status_code: int | None
    actor_type: ActorType
    confidence: ActorConfidence
    ai_agent_id: uuid.UUID | None
    # Denormalised at read time from the joined AiAgent, so a client that
    # only wants "which AI was this" never has to make a second request
    # per row. `None` for every row where `ai_agent_id` is `None` — a
    # human visit or a request from before any agent could be resolved -
    # and the field is `agent_signature`, not `agent_name`, because a
    # merchant-chosen display name can be renamed while the signature
    # (the join key access policies are written against) cannot.
    agent_signature: str | None = None
    purpose: AccessPurpose
    user_agent: str | None
    referrer_host: str | None
    # `ip_address` is present in the model but ABSENT here by default: see
    # `PageViewReadWithIp`, which is served only to OWNER/ADMIN. A viewer
    # role reading a traffic report has no need for the full address.
    ip_truncated: str | None
    ip_retained_until: datetime | None
    geo_method: GeoResolutionMethod
    geo_country: str | None
    geo_region: str | None
    geo_city: str | None
    geo_latitude: float | None
    geo_longitude: float | None
    geo_timezone: str | None
    occurred_at: datetime
    dwell_ms: int | None
    dwell_is_complete: bool
    access_decision: AccessDecision
    matched_policy_id: uuid.UUID | None


class PageViewReadWithIp(PageViewRead):
    """OWNER/ADMIN only. A separate model rather than a conditional field,
    so the narrower one cannot accidentally acquire the column."""

    ip_address: str | None


class ContentViewStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID | None
    path: str
    content_title: str | None
    content_type: str | None
    view_date: date
    human_views: int
    ai_crawler_views: int
    ai_answer_views: int
    agent_views: int
    search_views: int
    unknown_views: int
    total_views: int
    blocked_views: int
    payment_required_views: int
    dwell_ms_total: int
    dwell_samples: int
    distinct_countries: int
    # None when dwell_samples == 0. The UI shows "Not available", never 0s.
    mean_dwell_ms: float | None
    recomputed_at: datetime | None


class SearchDemandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_id: uuid.UUID
    demand_source: SearchDemandSource
    actor_type: ActorType
    ai_agent_id: uuid.UUID | None
    result_count: int | None
    path: str | None
    geo_country: str | None
    occurred_at: datetime


class SearchTermAggregate(BaseModel):
    query_id: uuid.UUID
    query_text: str
    normalized_query: str
    query_status: str
    search_count: int
    zero_result_count: int
    last_searched_at: datetime | None


# ---------------------------------------------------------------------------
# Access policy
# ---------------------------------------------------------------------------


class AccessPolicyWrite(BaseModel):
    agent_id: uuid.UUID | None = None
    actor_type: ActorType | None = None
    purpose: AccessPurpose | None = None
    tier: AccessTier
    reason: str | None = Field(default=None, max_length=2000)
    terms_url: str | None = Field(default=None, max_length=2048)
    # `specificity` is deliberately not accepted: a caller who could set it
    # could reorder the entire precedence table from outside.


class AccessPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None
    actor_type: ActorType | None
    purpose: AccessPurpose | None
    tier: AccessTier
    specificity: int
    reason: str | None
    terms_url: str | None
    updated_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AccessDecisionRead(BaseModel):
    decision: AccessDecision
    tier: AccessTier
    matched_policy_id: uuid.UUID | None
    reason: str | None
    terms_url: str | None
    http_status: int
    # Echoed back so an adapter can log what it was told about, and so a
    # support conversation has both halves.
    agent_id: uuid.UUID | None
    actor_type: ActorType
    confidence: ActorConfidence
    purpose: AccessPurpose


class TelemetryHealth(BaseModel):
    """Everything the dashboard's status strip needs, in one call.

    Deliberately NOT a single `ok: bool`. Phase 9's `AIOL_Status` rule
    stands: one green light that stays green while a dependency is down is
    a lie of omission an operator cannot act on.
    """

    core_reachable: bool
    database: str
    redis: str
    rate_limiting: str
    overall: str
    api_version: str
    core_version: str
    telemetry_events_last_24h: int
    last_event_at: datetime | None
    last_rollup_at: datetime | None
    agents_awaiting_decision: int
