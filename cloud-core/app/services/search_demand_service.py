"""
Search demand recording (Phase 13, ADR-081).

Turns "someone searched for X on our site" into a row, WITHOUT minting a
second query vocabulary. The find-or-create goes through Phase 6's
`normalize_query`, so a term typed by a customer and the same term
imported from Search Console resolve to one `Query` row and one demand
picture.

WHAT THIS SERVICE MAY NOT DO, AND WHY

It may not set `Query.status`. Phase 6 made CLASSIFIED a consequence of
having an Intent, never a manual assignment (ADR-015 family), and a
telemetry writer reaching in to change lifecycle state would be a second
owner of that field. It records occurrences; classification stays where
it lives.

It also may not create a `KnowledgeGap`. The checkpoint's UX-21 identified
the missing link between unanswered demand and gaps, and closing it is a
real piece of work with its own review — `zero_result_terms()` below
surfaces the candidates and stops there. Auto-creating gaps from search
misses would flood the gap list with typos.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_agent import AiAgent
from app.models.enums import ActorType, QueryPriority, QuerySource, QueryStatus, SearchDemandSource
from app.models.query import Query
from app.models.query_provenance import QueryProvenance
from app.models.search_demand_event import SearchDemandEvent
from app.schemas.common import SortParams, apply_sort
from app.services import ai_agent_service
from app.services.query_service import normalize_query


# Phase 13 demand source -> Phase 6 QuerySource. Explicit table rather
# than a default, so adding a demand source forces a deliberate choice
# here instead of silently landing in MANUAL.
_QUERY_SOURCE = {
    SearchDemandSource.ONSITE_SEARCH: QuerySource.SITE_SEARCH,
    SearchDemandSource.AGENT_QUERY: QuerySource.AI_TEST,
    SearchDemandSource.REFERRER_QUERY: QuerySource.SERP,
    SearchDemandSource.ADAPTER_REPORTED: QuerySource.SITE_SEARCH,
}


def _find_or_create_query(
    db: Session,
    *,
    organization_id: UUID,
    text: str,
    language: str,
    country: str | None,
    demand_source: SearchDemandSource,
) -> Query:
    normalized = normalize_query(text)
    query = db.execute(
        select(Query).where(
            Query.organization_id == organization_id,
            Query.normalized_query == normalized,
        )
    ).scalar_one_or_none()
    if query is not None:
        return query

    query = Query(
        organization_id=organization_id,
        query=text.strip()[:1000],
        normalized_query=normalized[:1000],
        language=language,
        country=country,
        # Phase 6's own vocabulary, reused as-is. `SITE_SEARCH` already
        # existed in section 23's closed source list, so Phase 13 adds no
        # value to a Phase 6 enum - a cross-phase schema change smuggled
        # in through a telemetry writer is exactly what §6 forbids.
        source=_QUERY_SOURCE[demand_source],
        status=QueryStatus.DISCOVERED,
        priority=QueryPriority.MEDIUM,
    )
    db.add(query)
    db.flush()
    return query


def record_search(
    db: Session,
    *,
    organization_id: UUID,
    site_id: UUID | None,
    event_key: str,
    search_text: str,
    demand_source: SearchDemandSource,
    occurred_at: datetime,
    user_agent: str | None = None,
    result_count: int | None = None,
    path: str | None = None,
    language: str = "fa",
    geo_country: str | None = None,
) -> SearchDemandEvent | None:
    """Record one search. Returns None if this `event_key` was already
    recorded — the adapter retries, and a retry must not double-count
    demand any more than it double-counts a page view."""
    existing = db.execute(
        select(SearchDemandEvent).where(
            SearchDemandEvent.organization_id == organization_id,
            SearchDemandEvent.event_key == event_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None

    if not search_text or not search_text.strip():
        return None

    query = _find_or_create_query(
        db,
        organization_id=organization_id,
        text=search_text,
        language=language,
        country=geo_country,
        demand_source=demand_source,
    )

    agent: AiAgent | None = None
    actor_type = ActorType.HUMAN
    if user_agent:
        agent = ai_agent_service.resolve_or_discover(
            db, organization_id=organization_id, user_agent=user_agent, observed_at=occurred_at
        )
        db.flush()
        actor_type = agent.actor_type

    # Phase 6 provenance: every occurrence appends, nothing overwrites.
    db.add(
        QueryProvenance(
            organization_id=organization_id,
            query_id=query.id,
            raw_query=search_text.strip()[:1000],
            source=_QUERY_SOURCE[demand_source],
        )
    )

    event = SearchDemandEvent(
        organization_id=organization_id,
        site_id=site_id,
        event_key=event_key,
        query_id=query.id,
        demand_source=demand_source,
        actor_type=actor_type,
        ai_agent_id=agent.id if agent else None,
        result_count=result_count,
        path=path,
        geo_country=geo_country,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.flush()
    return event


def list_demand(
    db: Session,
    *,
    organization_id: UUID,
    actor_type: ActorType | None = None,
    demand_source: SearchDemandSource | None = None,
    zero_results_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: SortParams | None = None,
) -> tuple[list[SearchDemandEvent], int]:
    stmt = select(SearchDemandEvent).where(
        SearchDemandEvent.organization_id == organization_id
    )
    if actor_type is not None:
        stmt = stmt.where(SearchDemandEvent.actor_type == actor_type)
    if demand_source is not None:
        stmt = stmt.where(SearchDemandEvent.demand_source == demand_source)
    if zero_results_only:
        # `== 0` and not `<= 0` or `IS NULL`: a NULL means "not reported",
        # which is not the same claim as "found nothing", and lumping them
        # together would put unmeasured searches into the content-gap list.
        stmt = stmt.where(SearchDemandEvent.result_count == 0)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, SearchDemandEvent, sort, default_field="occurred_at")
    return list(db.execute(stmt.limit(limit).offset(offset)).scalars().all()), total


def top_terms(
    db: Session,
    *,
    organization_id: UUID,
    actor_type: ActorType | None = None,
    zero_results_only: bool = False,
    ascending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Aggregated demand: term, how many times, how many found nothing.

    `ascending` exists because the owner asked to sort both directions,
    and because the bottom of this list is genuinely informative — a term
    searched twice that returns nothing may still be the next article.
    """
    searched = func.count(SearchDemandEvent.id)
    zero_hits = func.coalesce(
        func.sum(func.cast(SearchDemandEvent.result_count == 0, __import__("sqlalchemy").Integer)), 0
    )

    stmt = (
        select(
            Query.id.label("query_id"),
            Query.query.label("query_text"),
            Query.normalized_query.label("normalized_query"),
            Query.status.label("query_status"),
            searched.label("search_count"),
            zero_hits.label("zero_result_count"),
            func.max(SearchDemandEvent.occurred_at).label("last_searched_at"),
        )
        .join(Query, Query.id == SearchDemandEvent.query_id)
        .where(SearchDemandEvent.organization_id == organization_id)
        .group_by(Query.id, Query.query, Query.normalized_query, Query.status)
    )
    if actor_type is not None:
        stmt = stmt.where(SearchDemandEvent.actor_type == actor_type)
    if zero_results_only:
        stmt = stmt.where(SearchDemandEvent.result_count == 0)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    ordered = stmt.order_by(
        searched.asc() if ascending else searched.desc(), Query.id.asc()
    )
    rows = db.execute(ordered.limit(limit).offset(offset)).all()
    return [dict(r._mapping) for r in rows], total
