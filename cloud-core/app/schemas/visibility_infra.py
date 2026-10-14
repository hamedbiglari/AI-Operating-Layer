"""P12-18 / P12-19 contracts. No composite score anywhere."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    CompetitorOrigin,
    SearchDataSource,
    SearchSurface,
    VisibilityEventType,
    VisibilityPlatform,
    VisibilityProjectStatus,
    VisibilityRunStatus,
)


class VisibilityProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    markets: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    platforms: list[VisibilityPlatform] = Field(default_factory=list)
    target_brand: str | None = Field(default=None, max_length=200)
    target_domain: str | None = Field(default=None, max_length=255)
    site_id: uuid.UUID | None = None


class VisibilityProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    name: str
    description: str | None
    status: VisibilityProjectStatus
    markets: list
    languages: list
    platforms: list
    target_brand: str | None
    target_domain: str | None
    methodology_version: str
    created_at: datetime


class VisibilityRunCreate(BaseModel):
    platform: VisibilityPlatform
    provider_name: str = "not_configured"
    market: str | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, max_length=12)


class VisibilityRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    sync_job_id: uuid.UUID | None
    status: VisibilityRunStatus
    platform: VisibilityPlatform
    market: str | None
    language: str | None
    provider_name: str
    provider_version: str
    methodology_version: str
    queries_planned: int
    queries_observed: int
    queries_failed: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime


class VisibilityRunAccepted(BaseModel):
    """202 for an async run."""

    run_id: uuid.UUID
    status: VisibilityRunStatus
    job_id: uuid.UUID | None
    status_url: str


class VisibilitySnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID | None
    platform: VisibilityPlatform
    market: str | None
    language: str | None
    observations_total: int
    observations_tested: int
    observations_failed: int
    observations_unavailable: int
    mention_present: int
    citation_present: int
    recommendation_present: int
    product_present: int
    url_present: int
    methodology_version: str
    provider_name: str | None
    captured_at: datetime


class VisibilityRatesRead(BaseModel):
    """Sample-based rates. Every one carries its denominator and sample
    definition, and there is deliberately no overall score."""

    denominator: int
    sample: dict
    ai_mention_rate: float | None
    ai_citation_rate: float | None
    ai_recommendation_share: float | None
    ai_product_presence_rate: float | None
    caveat: str


class VisibilityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    event_type: VisibilityEventType
    platform: VisibilityPlatform | None
    subject: str | None
    previous_value: str | None
    current_value: str | None
    determination: str
    observed_at: datetime


class VisibilityCompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=255)
    origin: CompetitorOrigin = CompetitorOrigin.MERCHANT_DEFINED
    notes: str | None = None


class VisibilityCompetitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    domain: str
    origin: CompetitorOrigin
    is_approved: bool
    first_seen_at: datetime | None
    created_at: datetime


class SearchConsoleImportRequest(BaseModel):
    property_url: str = Field(min_length=1, max_length=500)
    start_date: date
    end_date: date
    provider_name: str | None = None
    market: str | None = Field(default=None, max_length=8)


class SerpObserveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    surface: SearchSurface = SearchSurface.GOOGLE_WEB
    market: str | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, max_length=12)
    depth: int = 10
    provider_name: str | None = None


class SearchImportResult(BaseModel):
    """`data_retrieved` is explicit: it separates "the provider returned
    nothing" from "the provider could not be reached"."""

    outcome: str
    imported: int
    duplicates: int = 0
    provider: str | None = None
    is_fixture: bool = False
    data_retrieved: bool
    error: str | None = None
    next_page_token: str | None = None


class SearchObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_id: uuid.UUID
    data_source: SearchDataSource
    surface: SearchSurface
    market: str | None
    language: str | None
    device: str | None
    observed_date: date
    position: float | None
    url: str | None
    title: str | None
    domain: str | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    provider_name: str
    is_fixture: bool
    collected_at: datetime


class SearchSummaryRead(BaseModel):
    observation_count: int
    position_denominator: int
    average_position: float | None
    top3_presence: int | None
    top10_presence: int | None
    total_impressions: int | None
    total_clicks: int | None
    caveats: list[str]
