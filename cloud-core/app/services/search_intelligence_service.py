"""
Search intelligence (P12-19, ADR-075).

REUSES the canonical Phase 6 `Query`. There is no SearchQuery table: a
search query IS a query, and a second one would fork the vocabulary the
rest of the system reasons about. An imported query that does not yet
exist is CREATED as a canonical Query with `source=search_console`, so
Phase 6 clustering and intent work on it immediately.

APPEND-ONLY. Re-importing the same day is idempotent via the uniqueness
constraint; it never overwrites, because overwriting destroys the history
the feature exists to provide.

ORIGINAL QUERY TEXT IS NEVER TRANSLATED OR REWRITTEN (§45). A Persian query
stays Persian; normalization for matching happens on a separate field.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    ProviderOutcome,
    QuerySource,
    SearchDataSource,
    SearchSurface,
)
from app.models.query import Query
from app.models.search_observation import SearchObservation
from app.services.audit import record_audit_log


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_query(
    db: Session, *, organization_id: UUID, text: str, source: QuerySource
) -> Query:
    """Finds or creates the canonical Query.

    The ORIGINAL text is stored verbatim. Phase 6 owns normalization; this
    module must not invent a second normalization rule or the two would
    disagree about what counts as the same query."""
    # Phase 6 owns normalization. Reusing its function rather than writing
    # a second one is what keeps the two from disagreeing about what
    # counts as the same query.
    from app.services.query_service import normalize_query

    normalized = normalize_query(text)

    existing = db.execute(
        select(Query).where(
            Query.organization_id == organization_id,
            Query.normalized_query == normalized,
        )
    ).scalars().first()
    if existing is not None:
        return existing

    query = Query(
        organization_id=organization_id,
        query=text,              # ORIGINAL text, verbatim (§45)
        normalized_query=normalized,
        source=source,
    )
    db.add(query)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.execute(
            select(Query).where(
                Query.organization_id == organization_id,
                Query.normalized_query == normalized,
            )
        ).scalars().first()
    return query


def import_search_console(
    db: Session, *, organization_id: UUID, property_url: str,
    start_date: date, end_date: date, provider_name: str | None = None,
    market: str | None = None, actor_user_id: UUID | None = None,
    page_token: str | None = None,
) -> dict:
    """Imports Search Console rows through the provider boundary.

    A provider failure is reported as a failure — never as zero rows.
    `AUTH_REQUIRED` and an empty successful response are different facts
    and the caller receives whichever actually occurred."""
    from app.integrations.search.fixture import get_console_provider

    provider = get_console_provider(provider_name)
    response = provider.fetch(
        property_url=property_url, start_date=start_date, end_date=end_date,
        market=market, page_token=page_token,
    )

    if not response.usable:
        return {
            "outcome": response.outcome.value,
            "imported": 0,
            "duplicates": 0,
            "error": response.error,
            "provider": response.provider_name,
            # Explicit: nothing was retrieved, which is NOT the same as
            # retrieving zero rows.
            "data_retrieved": False,
        }

    imported = duplicates = 0
    for row in response.rows:
        query = resolve_query(
            db, organization_id=organization_id, text=row.query,
            source=QuerySource.SEARCH_CONSOLE,
        )
        observation = SearchObservation(
            organization_id=organization_id,
            query_id=query.id,
            data_source=SearchDataSource.SEARCH_CONSOLE,
            surface=SearchSurface.GOOGLE_WEB,
            market=row.market,
            device=row.device,
            observed_date=row.observed_date,
            position=row.position,
            impressions=row.impressions,
            clicks=row.clicks,
            ctr=row.ctr,
            provider_name=response.provider_name,
            provider_version=response.provider_version,
            parser_version=response.parser_version,
            is_fixture=response.is_fixture,
            collected_at=_now(),
        )
        db.add(observation)
        try:
            db.flush()
            imported += 1
        except IntegrityError:
            # Append-only + idempotent: the same day re-imported is a
            # duplicate, not an error and not an overwrite.
            db.rollback()
            duplicates += 1

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="search_console.imported", resource_type="search_observation",
        resource_id=None,
        new_value={"imported": imported, "duplicates": duplicates,
                   "provider": response.provider_name, "is_fixture": response.is_fixture},
    )
    db.commit()
    return {
        "outcome": response.outcome.value, "imported": imported,
        "duplicates": duplicates, "provider": response.provider_name,
        "is_fixture": response.is_fixture, "next_page_token": response.next_page_token,
        "data_retrieved": True,
    }


def observe_serp(
    db: Session, *, organization_id: UUID, query_text: str,
    surface: SearchSurface = SearchSurface.GOOGLE_WEB, market: str | None = None,
    language: str | None = None, depth: int = 10, provider_name: str | None = None,
    actor_user_id: UUID | None = None,
) -> dict:
    """Observes one result page through the SERP boundary."""
    from app.integrations.search.base import SUPPORTED_DEPTHS
    from app.integrations.search.fixture import get_serp_provider

    if depth not in SUPPORTED_DEPTHS:
        raise ValueError(
            f"Unsupported depth {depth}. Allowed: {', '.join(map(str, SUPPORTED_DEPTHS))}."
        )

    provider = get_serp_provider(provider_name)
    response = provider.observe(
        query=query_text, surface=surface, market=market, language=language, depth=depth
    )
    if not response.usable:
        return {"outcome": response.outcome.value, "imported": 0,
                "error": response.error, "data_retrieved": False}

    query = resolve_query(
        db, organization_id=organization_id, text=query_text, source=QuerySource.MANUAL
    )
    imported = duplicates = 0
    for row in response.rows:
        observation = SearchObservation(
            organization_id=organization_id,
            query_id=query.id,
            data_source=SearchDataSource.SERP_PROVIDER,
            surface=surface,
            market=row.market, language=row.language,
            observed_date=row.observed_date,
            position=row.position, url=row.url, title=row.title,
            domain=row.domain, result_type=row.result_type,
            provider_name=response.provider_name,
            provider_version=response.provider_version,
            parser_version=response.parser_version,
            is_fixture=response.is_fixture,
            collected_at=_now(),
        )
        db.add(observation)
        try:
            db.flush()
            imported += 1
        except IntegrityError:
            db.rollback()
            duplicates += 1
    db.commit()
    return {"outcome": response.outcome.value, "imported": imported,
            "duplicates": duplicates, "provider": response.provider_name,
            "is_fixture": response.is_fixture, "data_retrieved": True}


def summarise(
    db: Session, *, organization_id: UUID, data_source: SearchDataSource | None = None,
    market: str | None = None,
) -> dict:
    """Descriptive metrics, computed in SQL and only where data exists.

    Every metric is None when its inputs are absent — never 0. A zero CTR
    and an unreported CTR are different facts, and averaging NULLs into
    zeros would understate every figure."""
    base = select(SearchObservation).where(
        SearchObservation.organization_id == organization_id
    )
    if data_source:
        base = base.where(SearchObservation.data_source == data_source)
    if market:
        base = base.where(SearchObservation.market == market)

    subquery = base.subquery()
    totals = db.execute(
        select(
            func.count(),
            func.avg(subquery.c.position),
            func.sum(subquery.c.impressions),
            func.sum(subquery.c.clicks),
            func.count(subquery.c.position),
        ).select_from(subquery)
    ).one()

    count, avg_position, impressions, clicks, position_rows = totals
    top3 = db.execute(
        select(func.count()).select_from(subquery).where(subquery.c.position <= 3)
    ).scalar_one()
    top10 = db.execute(
        select(func.count()).select_from(subquery).where(subquery.c.position <= 10)
    ).scalar_one()

    return {
        "observation_count": count,
        # Denominator for position-based metrics is the number of rows that
        # actually carry a position, not the total.
        "position_denominator": position_rows,
        "average_position": round(float(avg_position), 2) if avg_position is not None else None,
        "top3_presence": top3 if position_rows else None,
        "top10_presence": top10 if position_rows else None,
        "total_impressions": int(impressions) if impressions is not None else None,
        "total_clicks": int(clicks) if clicks is not None else None,
        "caveats": [
            "Metrics are computed only where the underlying data exists. "
            "A null metric means the source did not report it, which is not zero.",
            "Search observations are distinct from AI visibility observations "
            "and are never combined.",
        ],
    }
