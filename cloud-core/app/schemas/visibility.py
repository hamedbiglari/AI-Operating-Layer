"""Phase 12 contracts. No composite score appears anywhere by design."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    SignalPresence,
    VisibilityCollectionMethod,
    VisibilityPlatform,
    VisibilityTestType,
)


class VisibilityObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    query_id: uuid.UUID | None
    product_id: uuid.UUID | None
    platform: VisibilityPlatform
    test_type: VisibilityTestType
    prompt: str
    response: str | None
    mentioned: SignalPresence
    cited: SignalPresence
    recommended: SignalPresence
    product_present: SignalPresence
    url_present: SignalPresence
    collection_method: VisibilityCollectionMethod
    platform_model: str | None
    result_metadata: dict
    tested_at: datetime
    estimated_cost: float | None
    # Phase 17: the AIExecution this observation was parsed from (NULL for
    # fixture / not-configured / manually recorded observations).
    ai_execution_id: uuid.UUID | None = None
    created_at: datetime


class VisibilityObservationCreate(BaseModel):
    """`tested_at` is REQUIRED, not defaulted.

    An observation pasted from yesterday's session happened yesterday.
    Stamping it with the import time would silently corrupt every time
    series built on this table, and the corruption would be invisible."""

    platform: VisibilityPlatform
    test_type: VisibilityTestType
    prompt: str = Field(min_length=1)
    tested_at: datetime
    response: str | None = None
    query_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    # Every signal defaults to NOT_CHECKED. A caller that did not look at a
    # signal says nothing about it, rather than implicitly asserting absence.
    mentioned: SignalPresence = SignalPresence.NOT_CHECKED
    cited: SignalPresence = SignalPresence.NOT_CHECKED
    recommended: SignalPresence = SignalPresence.NOT_CHECKED
    product_present: SignalPresence = SignalPresence.NOT_CHECKED
    url_present: SignalPresence = SignalPresence.NOT_CHECKED
    collection_method: VisibilityCollectionMethod = VisibilityCollectionMethod.MANUAL_PASTE
    platform_model: str | None = Field(default=None, max_length=120)
    result_metadata: dict = Field(default_factory=dict)
    estimated_cost: float | None = Field(default=None, ge=0)


class SignalCounts(BaseModel):
    """Three counts and an honest denominator.

    `checked` is present + absent. It is NOT the observation total, because
    observations that never examined this signal must not silently enlarge
    a denominator and deflate an apparent rate."""

    present: int
    absent: int
    not_checked: int
    checked: int


class VisibilityPlatformCount(BaseModel):
    platform: str
    observations: int
    last_observed_at: datetime


class VisibilitySummary(BaseModel):
    """Counts and coverage. Deliberately contains no score, no percentage
    and no ranking — see ADR-064."""

    observation_count: int
    signals: dict[str, SignalCounts]
    by_collection_method: dict[str, int]
    by_platform: list[VisibilityPlatformCount]   # most observations first (V5-visibility-platform-breakdown)
    caveats: list[str]
    as_of: datetime


class VisibilityBudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    period_key: str
    currency: str
    period_limit: float
    period_spent: float
    last_reconciled_at: datetime | None


class VisibilityBudgetUpdate(BaseModel):
    period_limit: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class VisibilityCountryCount(BaseModel):
    country: str
    requests: int


class VisibilityKeyCount(BaseModel):
    key: str
    requests: int


class VisibilityDayCount(BaseModel):
    day: date
    observations: int
    requests: int


class VisibilityAggregates(BaseModel):
    """The visibility report's numbers for a rolling window, in one response (V5-visibility-detail-aggregates).
    Counts of stored rows only: no score, no estimate; unknown actors and missing countries are reported, not
    folded in or guessed."""

    days: int
    since: datetime
    until: datetime
    platform_observations: int
    automated_requests: int
    unclassified_requests: int
    countries_reached: int
    top_country: VisibilityCountryCount | None
    requests_without_country: int
    mean_dwell_ms: int | None
    dwell_samples: int
    by_day: list[VisibilityDayCount]
    by_country: list[VisibilityCountryCount]
    by_actor_type: list[VisibilityKeyCount]
    top_pages: list[VisibilityKeyCount]
