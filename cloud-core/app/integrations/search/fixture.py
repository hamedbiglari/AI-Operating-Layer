"""
Deterministic search fixtures (P12-19 §35).

Realistic shapes: multiple queries, dates, countries, devices, positions,
impressions and CTR, plus rows with MISSING dimensions — because the
normalizer's hardest job is distinguishing "not reported" from "zero", and
a fixture where everything is populated would never test it.

Every row carries `is_fixture=True`, which persists onto the observation.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.integrations.search.base import (
    SearchConsoleRow,
    SearchProviderResponse,
    SerpRow,
)
from app.models.enums import ProviderOutcome, SearchResultType, SearchSurface


class FixtureSearchConsoleProvider:
    name = "fixture_search_console"
    version = "1.0"

    def fetch(
        self, *, property_url: str, start_date: date, end_date: date,
        market: str | None = None, page_token: str | None = None, limit: int = 1000,
    ) -> SearchProviderResponse:
        if "[authrequired]" in property_url:
            return SearchProviderResponse(
                outcome=ProviderOutcome.AUTH_REQUIRED, error="Token expired",
                provider_name=self.name, provider_version=self.version, is_fixture=True,
            )
        if "[ratelimited]" in property_url:
            return SearchProviderResponse(
                outcome=ProviderOutcome.RATE_LIMITED, error="Quota exceeded",
                provider_name=self.name, provider_version=self.version, is_fixture=True,
            )
        if "[empty]" in property_url:
            # A genuine zero-result day: SUCCESS with no rows. Distinct from
            # AUTH_REQUIRED above, which is the whole point.
            return SearchProviderResponse(
                outcome=ProviderOutcome.SUCCESS, rows=[],
                provider_name=self.name, provider_version=self.version, is_fixture=True,
            )

        day = start_date
        rows = [
            SearchConsoleRow(query="taranjabin benefits", observed_date=day, market="US",
                             device="DESKTOP", impressions=1200, clicks=84, ctr=0.07,
                             position=4.2),
            SearchConsoleRow(query="taranjabin benefits", observed_date=day, market="GB",
                             device="MOBILE", impressions=340, clicks=12, ctr=0.035,
                             position=7.8),
            SearchConsoleRow(query="خواص ترنجبین", observed_date=day, market="IR",
                             device="MOBILE", impressions=980, clicks=131, ctr=0.134,
                             position=2.1),
            # Missing device and CTR: the source did not report them. NULL,
            # never zero.
            SearchConsoleRow(query="where to buy taranjabin", observed_date=day,
                             market="US", device=None, impressions=210, clicks=None,
                             ctr=None, position=11.4),
            SearchConsoleRow(query="taranjabin price", observed_date=day + timedelta(days=1),
                             market="US", device="DESKTOP", impressions=75, clicks=3,
                             ctr=0.04, position=15.0),
        ]
        if page_token == "page2":
            rows = [SearchConsoleRow(query="taranjabin wholesale", observed_date=day,
                                     market="US", device="DESKTOP", impressions=45,
                                     clicks=2, ctr=0.044, position=19.2)]
            return SearchProviderResponse(
                outcome=ProviderOutcome.SUCCESS, rows=rows, provider_name=self.name,
                provider_version=self.version, is_fixture=True,
            )
        return SearchProviderResponse(
            outcome=ProviderOutcome.SUCCESS, rows=rows[:limit],
            provider_name=self.name, provider_version=self.version,
            next_page_token="page2", is_fixture=True,
        )


class FixtureSerpProvider:
    name = "fixture_serp"
    version = "1.0"

    def observe(
        self, *, query: str, surface: SearchSurface, market: str | None = None,
        language: str | None = None, depth: int = 10,
    ) -> SearchProviderResponse:
        if "[unavailable]" in query.lower():
            return SearchProviderResponse(
                outcome=ProviderOutcome.UNAVAILABLE, error="Provider unreachable",
                provider_name=self.name, provider_version=self.version, is_fixture=True,
            )

        today = date.today()
        catalogue = [
            ("https://merchant.example/taranjabin", "Taranjabin — merchant",
             "merchant.example", SearchResultType.ORGANIC),
            ("https://competitor-a.example/taranjabin", "Competitor A",
             "competitor-a.example", SearchResultType.ORGANIC),
            ("https://wikipedia.org/wiki/Taranjabin", "Taranjabin - Wikipedia",
             "wikipedia.org", SearchResultType.ORGANIC),
            ("https://competitor-b.example/shop", "Competitor B shop",
             "competitor-b.example", SearchResultType.SHOPPING),
            ("https://news.example/taranjabin-harvest", "Harvest report",
             "news.example", SearchResultType.OTHER),
        ]
        rows = [
            SerpRow(query=query, observed_date=today, position=float(i + 1), url=url,
                    title=title, domain=domain, result_type=rtype, market=market,
                    language=language)
            for i, (url, title, domain, rtype) in enumerate(catalogue[:depth])
        ]
        return SearchProviderResponse(
            outcome=ProviderOutcome.SUCCESS, rows=rows, provider_name=self.name,
            provider_version=self.version, is_fixture=True,
        )


_CONSOLE: dict[str, object] = {}
_SERP: dict[str, object] = {}


def register_console(provider) -> None:
    _CONSOLE[provider.name] = provider


def register_serp(provider) -> None:
    _SERP[provider.name] = provider


def get_console_provider(name: str | None = None):
    from app.integrations.search.base import NotConfiguredSearchConsoleProvider

    if not name:
        return NotConfiguredSearchConsoleProvider()
    return _CONSOLE.get(name) or NotConfiguredSearchConsoleProvider()


def get_serp_provider(name: str | None = None):
    from app.integrations.search.base import NotConfiguredSerpProvider

    if not name:
        return NotConfiguredSerpProvider()
    return _SERP.get(name) or NotConfiguredSerpProvider()


register_console(FixtureSearchConsoleProvider())
register_serp(FixtureSerpProvider())
