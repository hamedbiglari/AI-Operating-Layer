"""
Telemetry ingestion and reporting (Phase 13, ADR-078/079/080).

Responsibilities, in order of how much can go wrong:

    ingest_batch()      write page views idempotently
    rollup_day()        derive the daily content aggregate
    enforce_retention() null full IP addresses past their horizon

IDEMPOTENCY IS NOT OPTIONAL

The adapter batches observations and retries on network failure. Without
a client-minted `event_key` and a unique constraint behind it, one retry
inflates every count on the merchant's dashboard and there is no way to
tell afterwards. So a redelivered batch is accepted, silently deduplicated,
and the response reports `accepted` and `duplicates` separately — the
caller is told, rather than the duplicate being hidden.

IP TRUNCATION HAPPENS AT WRITE TIME

`ip_truncated` is computed here, not at read time, because the retention
job later destroys `ip_address` and the truncated form has to survive it.
Computing it lazily would mean losing it exactly when it becomes the only
copy.

GEOLOCATION IS PASSED THROUGH, NEVER DERIVED

If the adapter supplied a country, it is stored with
`geo_method=ADAPTER_REPORTED` or `EDGE_HEADER`. If it did not, every geo
column stays NULL and `geo_method=NONE`. This service performs no IP
lookup, has no database to look up in, and makes no network call. See
ADR-079 for why that is a design decision and not an omission.
"""

import ipaddress
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Integer, case, func, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.content_view_daily import ContentViewDaily
from app.models.enums import AccessDecision, ActorType, GeoResolutionMethod
from app.models.page_view import PageView
from app.schemas.common import SortParams, apply_sort
from app.services import access_policy_service, ai_agent_service

# Default horizon for the full IP address. Organization-configurable in a
# later phase; a constant with a documented default beats a settings knob
# nobody has asked for yet.
DEFAULT_IP_RETENTION_DAYS = 30

# ~1 km. Enough to say "Tehran"; not enough to say "this street".
_GEO_PRECISION = 2


@dataclass(frozen=True)
class IngestResult:
    accepted: int
    duplicates: int
    rejected: int
    agents_discovered: int
    errors: list[str]


def truncate_ip(raw: str | None) -> str | None:
    """/24 for IPv4, /48 for IPv6. Returns None for anything unparseable —
    never the raw string, because a fallback that returns the input would
    turn a malformed address into an un-truncated one, which is the exact
    failure this function exists to prevent."""
    if not raw:
        return None
    try:
        addr = ipaddress.ip_address(raw.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{addr}/24", strict=False))
    return str(ipaddress.ip_network(f"{addr}/48", strict=False))


def _round_coord(value: float | None) -> float | None:
    return None if value is None else round(float(value), _GEO_PRECISION)


def ingest_batch(
    db: Session,
    *,
    organization_id: UUID,
    site_id: UUID | None,
    events: list,
    ip_retention_days: int = DEFAULT_IP_RETENTION_DAYS,
) -> IngestResult:
    """Write a batch of page views. `events` are `PageViewIngest` schemas.

    One flush per event so that a single malformed row is rejected on its
    own rather than poisoning the batch. Slower than one bulk insert, and
    deliberately so: an adapter that sends 200 events and gets back "all
    rejected, one of them was bad" cannot act on that.
    """
    accepted = duplicates = rejected = discovered = 0
    errors: list[str] = []
    now = utcnow()

    existing_keys = set(
        db.execute(
            select(PageView.event_key).where(
                PageView.organization_id == organization_id,
                PageView.event_key.in_([e.event_key for e in events]),
            )
        ).scalars().all()
    )

    for event in events:
        if event.event_key in existing_keys:
            duplicates += 1
            continue

        try:
            agent = None
            if event.user_agent:
                before = ai_agent_service.fingerprint(event.user_agent)
                agent = ai_agent_service.resolve_or_discover(
                    db,
                    organization_id=organization_id,
                    user_agent=event.user_agent,
                    observed_at=event.occurred_at,
                )
                db.flush()
                if agent.observation_count == 1 and agent.signature == before:
                    discovered += 1

            actor_type = agent.actor_type if agent else ActorType.UNKNOWN
            confidence, purpose = (
                (agent.confidence, agent.declared_purpose) if agent else (None, None)
            )

            evaluation = access_policy_service.evaluate(
                db,
                organization_id=organization_id,
                agent_id=agent.id if agent else None,
                actor_type=actor_type,
                purpose=purpose or event.purpose,
            )

            ip_raw = str(event.ip_address) if event.ip_address else None
            truncated = truncate_ip(ip_raw)
            retained_until = (
                now + timedelta(days=ip_retention_days) if ip_raw else None
            )

            geo_method = event.geo_method or (
                GeoResolutionMethod.NONE
                if event.geo_country is None
                else GeoResolutionMethod.ADAPTER_REPORTED
            )

            view = PageView(
                organization_id=organization_id,
                site_id=site_id or event.site_id,
                event_key=event.event_key,
                path=event.path[:512],
                content_type=event.content_type,
                content_title=event.content_title,
                status_code=event.status_code,
                actor_type=actor_type,
                confidence=confidence or event.confidence,
                ai_agent_id=agent.id if agent else None,
                purpose=purpose or event.purpose,
                user_agent=(event.user_agent or None),
                referrer_host=event.referrer_host,
                ip_address=ip_raw,
                ip_truncated=truncated,
                ip_retained_until=retained_until,
                geo_method=geo_method,
                geo_country=event.geo_country,
                geo_region=event.geo_region,
                geo_city=event.geo_city,
                geo_latitude=_round_coord(event.geo_latitude),
                geo_longitude=_round_coord(event.geo_longitude),
                geo_timezone=event.geo_timezone,
                occurred_at=event.occurred_at,
                dwell_ms=event.dwell_ms,
                dwell_is_complete=bool(event.dwell_is_complete),
                access_decision=evaluation.decision,
                matched_policy_id=evaluation.matched_policy_id,
            )
            db.add(view)
            db.flush()
            existing_keys.add(event.event_key)
            accepted += 1
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            db.rollback()
            rejected += 1
            errors.append(f"{event.event_key}: {type(exc).__name__}")

    return IngestResult(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        agents_discovered=discovered,
        errors=errors,
    )


def _count_when(condition) -> object:
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def rollup_day(
    db: Session, *, organization_id: UUID, view_date: date, site_id: UUID | None = None
) -> int:
    """Recompute `content_view_daily` for one day from `page_views`.

    Full recompute of the day, not an increment. An incremental counter
    that drifts is undetectable; a recompute that can be re-run at any
    time is verifiable by re-running it, which is what the mutation test
    for this function does.

    Returns the number of rollup rows written.
    """
    start = datetime.combine(view_date, datetime.min.time()).replace(
        tzinfo=utcnow().tzinfo
    )
    end = start + timedelta(days=1)

    stmt = (
        select(
            PageView.site_id,
            PageView.path,
            func.max(PageView.content_title).label("content_title"),
            func.max(PageView.content_type).label("content_type"),
            _count_when(PageView.actor_type == ActorType.HUMAN).label("human_views"),
            _count_when(PageView.actor_type == ActorType.AI_CRAWLER).label("ai_crawler_views"),
            _count_when(PageView.actor_type == ActorType.AI_USER_AGENT).label("ai_answer_views"),
            _count_when(PageView.actor_type == ActorType.AGENT_TOOL).label("agent_views"),
            _count_when(PageView.actor_type == ActorType.SEARCH_CRAWLER).label("search_views"),
            _count_when(PageView.actor_type == ActorType.UNKNOWN).label("unknown_views"),
            _count_when(PageView.access_decision == AccessDecision.BLOCKED).label("blocked_views"),
            _count_when(PageView.access_decision == AccessDecision.PAYMENT_REQUIRED).label("payment_required_views"),
            func.coalesce(func.sum(PageView.dwell_ms), 0).label("dwell_ms_total"),
            func.coalesce(
                func.sum(case((PageView.dwell_ms.isnot(None), 1), else_=0)), 0
            ).label("dwell_samples"),
            func.count(func.distinct(PageView.geo_country)).cast(Integer).label("distinct_countries"),
        )
        .where(
            PageView.organization_id == organization_id,
            PageView.occurred_at >= start,
            PageView.occurred_at < end,
        )
        .group_by(PageView.site_id, PageView.path)
    )
    if site_id is not None:
        stmt = stmt.where(PageView.site_id == site_id)

    rows = db.execute(stmt).all()
    now = utcnow()
    written = 0

    for row in rows:
        total = (
            row.human_views
            + row.ai_crawler_views
            + row.ai_answer_views
            + row.agent_views
            + row.search_views
            + row.unknown_views
        )
        existing = db.execute(
            select(ContentViewDaily).where(
                ContentViewDaily.organization_id == organization_id,
                ContentViewDaily.site_id.is_(row.site_id) if row.site_id is None else ContentViewDaily.site_id == row.site_id,
                ContentViewDaily.path == row.path,
                ContentViewDaily.view_date == view_date,
            )
        ).scalar_one_or_none()

        target = existing or ContentViewDaily(
            organization_id=organization_id,
            site_id=row.site_id,
            path=row.path,
            view_date=view_date,
        )
        target.content_title = row.content_title
        target.content_type = row.content_type
        target.human_views = row.human_views
        target.ai_crawler_views = row.ai_crawler_views
        target.ai_answer_views = row.ai_answer_views
        target.agent_views = row.agent_views
        target.search_views = row.search_views
        target.unknown_views = row.unknown_views
        target.blocked_views = row.blocked_views
        target.payment_required_views = row.payment_required_views
        target.dwell_ms_total = row.dwell_ms_total
        target.dwell_samples = row.dwell_samples
        target.distinct_countries = row.distinct_countries
        target.total_views = total
        target.recomputed_at = now
        if existing is None:
            db.add(target)
        written += 1

    db.flush()
    return written


def enforce_retention(db: Session, *, organization_id: UUID | None = None, now=None) -> int:
    """Null every `ip_address` whose horizon has passed.

    `ip_truncated` is untouched, so every report keeps working at /24
    granularity forever. This is the function that makes the collection of
    a full IP defensible; it is scheduled, tested with a boundary case on
    both sides of the horizon, and its absence would silently turn a
    30-day window into permanent retention.
    """
    moment = now or utcnow()
    stmt = (
        update(PageView)
        .where(
            PageView.ip_address.isnot(None),
            PageView.ip_retained_until.isnot(None),
            PageView.ip_retained_until <= moment,
        )
        .values(ip_address=None, ip_retained_until=None)
    )
    if organization_id is not None:
        stmt = stmt.where(PageView.organization_id == organization_id)
    result = db.execute(stmt)
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def signatures_for(db: Session, *, organization_id: UUID, agent_ids) -> dict:
    """Batched id -> signature lookup for denormalising `PageViewRead`.

    One query with an IN clause, not one query per row: a page of 50
    page-views must not become 50 extra round trips just to show which
    agent made each request. Called once per response, at the API
    boundary — `list_page_views` itself stays a plain `PageView` query so
    its contract (and `apply_sort`'s allow-list) is untouched.
    """
    from app.models.ai_agent import AiAgent

    ids = {i for i in agent_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(AiAgent.id, AiAgent.signature).where(
            AiAgent.organization_id == organization_id,
            AiAgent.id.in_(ids),
        )
    ).all()
    return {row.id: row.signature for row in rows}


def list_page_views(
    db: Session,
    *,
    organization_id: UUID,
    actor_type: ActorType | None = None,
    path: str | None = None,
    geo_country: str | None = None,
    agent_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: SortParams | None = None,
) -> tuple[list[PageView], int]:
    stmt = select(PageView).where(PageView.organization_id == organization_id)
    if actor_type is not None:
        stmt = stmt.where(PageView.actor_type == actor_type)
    if path is not None:
        stmt = stmt.where(PageView.path == path)
    if geo_country is not None:
        stmt = stmt.where(PageView.geo_country == geo_country)
    if agent_id is not None:
        stmt = stmt.where(PageView.ai_agent_id == agent_id)
    if occurred_from is not None:
        stmt = stmt.where(PageView.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(PageView.occurred_at < occurred_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, PageView, sort, default_field="occurred_at")
    return list(db.execute(stmt.limit(limit).offset(offset)).scalars().all()), total


def list_content_stats(
    db: Session,
    *,
    organization_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    content_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: SortParams | None = None,
) -> tuple[list[ContentViewDaily], int]:
    """The report behind "sort my content by how often it was seen".

    Server-side ordering and paging, per the performance gate: the client
    never receives the whole collection to sort in the browser.
    """
    stmt = select(ContentViewDaily).where(
        ContentViewDaily.organization_id == organization_id
    )
    if date_from is not None:
        stmt = stmt.where(ContentViewDaily.view_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ContentViewDaily.view_date <= date_to)
    if content_type is not None:
        stmt = stmt.where(ContentViewDaily.content_type == content_type)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, ContentViewDaily, sort, default_field="total_views")
    return list(db.execute(stmt.limit(limit).offset(offset)).scalars().all()), total
