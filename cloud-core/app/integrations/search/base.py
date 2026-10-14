"""
Search intelligence provider boundary (P12-19, ADR-075).

Two provider kinds, deliberately separate because they answer different
questions:

    SearchConsoleProvider   first-party performance data for MY pages:
                            impressions, clicks, CTR, average position
    SerpProvider            an external observation of a result PAGE:
                            position, URL, title, domain, result type

Merging them would force half-null rows with no way to tell a missing
metric from an unmeasured one (§24).

FAILURE IS NEVER AN EMPTY LIST. Every response carries a `ProviderOutcome`.
A provider that returns `rows=[]` with `outcome=SUCCESS` is asserting "I
looked and there was nothing"; one that cannot run must say UNAVAILABLE,
AUTH_REQUIRED or NOT_CONFIGURED instead (§27).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models.enums import ProviderOutcome, SearchResultType, SearchSurface


@dataclass
class SearchConsoleRow:
    """One normalized Search Console row.

    Every metric is optional: Search Console omits dimensions depending on
    the request, and a zero would claim a measurement that was not made."""

    query: str
    observed_date: date
    market: str | None = None
    device: str | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    position: float | None = None


@dataclass
class SerpRow:
    """One normalized SERP result."""

    query: str
    observed_date: date
    position: float
    url: str
    title: str | None = None
    domain: str | None = None
    result_type: SearchResultType = SearchResultType.ORGANIC
    market: str | None = None
    language: str | None = None


@dataclass
class SearchProviderResponse:
    """Outcome first, rows second — the ordering reflects which one a
    caller must check."""

    outcome: ProviderOutcome
    rows: list = field(default_factory=list)
    error: str | None = None
    provider_name: str = "unknown"
    provider_version: str = "unknown"
    parser_version: str = "v1"
    next_page_token: str | None = None
    estimated_cost: float | None = 0.0
    is_fixture: bool = False

    @property
    def usable(self) -> bool:
        return self.outcome in (ProviderOutcome.SUCCESS, ProviderOutcome.PARTIAL)


class SearchConsoleProvider(Protocol):
    name: str
    version: str

    def fetch(
        self, *, property_url: str, start_date: date, end_date: date,
        market: str | None = None, page_token: str | None = None, limit: int = 1000,
    ) -> SearchProviderResponse:
        ...


class SerpProvider(Protocol):
    name: str
    version: str

    def observe(
        self, *, query: str, surface: SearchSurface, market: str | None = None,
        language: str | None = None, depth: int = 10,
    ) -> SearchProviderResponse:
        ...


# Observation depths the SERP boundary accepts. Closed set, because an
# arbitrary depth is a cost multiplier a caller should not choose freely.
SUPPORTED_DEPTHS = (1, 3, 5, 10, 20, 50, 100, 200)


class NotConfiguredSearchConsoleProvider:
    """**Default.** No Google credentials exist here and none are invented.

    Returns AUTH_REQUIRED rather than an empty success, because an empty
    success would be indistinguishable from a property that genuinely had
    no impressions."""

    name = "not_configured_search_console"
    version = "1.0"

    def fetch(
        self, *, property_url: str, start_date: date, end_date: date,
        market: str | None = None, page_token: str | None = None, limit: int = 1000,
    ) -> SearchProviderResponse:
        return SearchProviderResponse(
            outcome=ProviderOutcome.AUTH_REQUIRED,
            error=(
                "No Search Console credentials are configured. No data was "
                "retrieved; this is not evidence of zero impressions."
            ),
            provider_name=self.name, provider_version=self.version,
        )


class NotConfiguredSerpProvider:
    """**Default.** No SERP provider is configured; nothing is scraped."""

    name = "not_configured_serp"
    version = "1.0"

    def observe(
        self, *, query: str, surface: SearchSurface, market: str | None = None,
        language: str | None = None, depth: int = 10,
    ) -> SearchProviderResponse:
        return SearchProviderResponse(
            outcome=ProviderOutcome.NOT_CONFIGURED,
            error=(
                "No SERP provider is configured. No result page was observed; "
                "this is not evidence of absence from search results."
            ),
            provider_name=self.name, provider_version=self.version,
        )
