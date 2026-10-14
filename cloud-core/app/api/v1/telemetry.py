"""
Phase 13 telemetry, analytics and AI access API.

TWO AUDIENCES, TWO AUTHENTICATION SCHEMES, ON PURPOSE

    /telemetry/ingest/*     machine identity (adapter)   scope telemetry:write
    /telemetry/*  (reads)   user session (dashboard)     role-checked

They do not share a dependency. An adapter credential can report traffic
and read back its own aggregates; it can never edit a policy, and a user
token is never accepted on an ingest route. Mixing them would mean one
leaked plugin credential could change what the merchant's site allows.

EVERY LIST IS SERVER-PAGED AND SERVER-SORTED

Through `SortParams`/`apply_sort`, the same canonical implementation every
other list endpoint in this project uses (ADR-056). Sorting is not
re-implemented here, and an unknown `sort_by` is a 422 naming the allowed
values rather than a silent fallback.
"""

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query as Q, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.session import get_db
from app.models.access_policy import AccessPolicy
from app.models.ai_agent import AiAgent
from app.models.content_view_daily import ContentViewDaily
from app.models.enums import (
    AccessPurpose,
    AccessTier,
    ActorType,
    AdapterScope,
    AgentRegistrationOrigin,
    SearchDemandSource,
    UserRole,
)
from app.models.page_view import PageView
from app.models.user import User
from app.schemas.common import Page, SortParams, sortable_fields
from app.schemas.telemetry import (
    AccessDecisionRead,
    AccessPolicyRead,
    AccessPolicyWrite,
    AiAgentRead,
    AiAgentRename,
    ContentViewStatRead,
    IngestResponse,
    PageViewBatch,
    PageViewRead,
    PageViewReadWithIp,
    SearchDemandBatch,
    SearchDemandRead,
    SearchTermAggregate,
    TelemetryHealth,
)
from app.security.dependencies import get_current_user, require_roles
from app.security.machine_identity import MachineIdentity, require_scope
from app.security.tenant import get_tenant_scoped_or_404
from app.services import (
    access_policy_service,
    ai_agent_service,
    search_demand_service,
    telemetry_service,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Bumped whenever a response shape changes. The dashboard displays it so a
# merchant reporting a bug can say which contract they were talking to.
TELEMETRY_API_VERSION = "13.0"


def _sort(sort_by: str | None, sort_dir: str | None) -> SortParams:
    return SortParams(sort_by=sort_by, sort_dir=sort_dir)


# ===========================================================================
# Ingest — adapter only
# ===========================================================================


@router.post(
    "/ingest/page-views",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_page_views(
    payload: PageViewBatch,
    identity: MachineIdentity = Depends(require_scope(AdapterScope.TELEMETRY_WRITE)),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """202, not 201. The batch is accepted and durably written, but the
    daily rollup that the reports read is recomputed separately, so the
    caller has not been told "your dashboard is updated"."""
    result = telemetry_service.ingest_batch(
        db,
        organization_id=identity.organization_id,
        site_id=identity.site_id,
        events=payload.events,
    )
    db.commit()
    return IngestResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        rejected=result.rejected,
        agents_discovered=result.agents_discovered,
        errors=result.errors,
    )


@router.post(
    "/ingest/search",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_search(
    payload: SearchDemandBatch,
    identity: MachineIdentity = Depends(require_scope(AdapterScope.TELEMETRY_WRITE)),
    db: Session = Depends(get_db),
) -> IngestResponse:
    accepted = duplicates = rejected = 0
    errors: list[str] = []
    for event in payload.events:
        try:
            created = search_demand_service.record_search(
                db,
                organization_id=identity.organization_id,
                site_id=identity.site_id or event.site_id,
                event_key=event.event_key,
                search_text=event.search_text,
                demand_source=event.demand_source,
                occurred_at=event.occurred_at,
                user_agent=event.user_agent,
                result_count=event.result_count,
                path=event.path,
                language=event.language,
                geo_country=event.geo_country,
            )
            if created is None:
                duplicates += 1
            else:
                accepted += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            rejected += 1
            errors.append(f"{event.event_key}: {type(exc).__name__}")
    db.commit()
    return IngestResponse(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        agents_discovered=0,
        errors=errors,
    )


@router.get("/access-decision", response_model=AccessDecisionRead)
def evaluate_access(
    user_agent: str = Q(..., max_length=400),
    purpose: AccessPurpose | None = Q(default=None),
    identity: MachineIdentity = Depends(require_scope(AdapterScope.TELEMETRY_READ)),
    db: Session = Depends(get_db),
) -> AccessDecisionRead:
    """Authoritative evaluation, for an adapter that wants Core to decide.

    The plugin caches its own copy of the policy table and decides at the
    edge, because a network round trip inside `template_redirect` is not
    acceptable. This endpoint exists so that decision can be audited
    against the source of truth, and so a non-caching client has a correct
    path. Two implementations of one rule is a duplication risk, and it is
    answered by `test_phase13_edge_parity` asserting they agree.
    """
    agent = ai_agent_service.resolve_or_discover(
        db, organization_id=identity.organization_id, user_agent=user_agent
    )
    db.flush()
    effective_purpose = purpose or agent.declared_purpose
    evaluation = access_policy_service.evaluate(
        db,
        organization_id=identity.organization_id,
        agent_id=agent.id,
        actor_type=agent.actor_type,
        purpose=effective_purpose,
    )
    db.commit()
    return AccessDecisionRead(
        decision=evaluation.decision,
        tier=evaluation.tier,
        matched_policy_id=evaluation.matched_policy_id,
        reason=evaluation.reason,
        terms_url=evaluation.terms_url,
        http_status=evaluation.http_status,
        agent_id=agent.id,
        actor_type=agent.actor_type,
        confidence=agent.confidence,
        purpose=effective_purpose,
    )


# ===========================================================================
# Reports — dashboard
# ===========================================================================


@router.get("/page-views", response_model=Page[PageViewRead])
def list_page_views(
    actor_type: ActorType | None = None,
    path: str | None = None,
    geo_country: str | None = Q(default=None, min_length=2, max_length=2),
    agent_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[PageViewRead]:
    rows, total = telemetry_service.list_page_views(
        db,
        organization_id=current_user.organization_id,
        actor_type=actor_type,
        path=path,
        geo_country=geo_country.upper() if geo_country else None,
        agent_id=agent_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    signatures = telemetry_service.signatures_for(
        db, organization_id=current_user.organization_id,
        agent_ids=[r.ai_agent_id for r in rows],
    )
    items = []
    for r in rows:
        payload = PageViewRead.model_validate(r).model_dump()
        # A human visit carries no agent signature: every client gets a
        # registry row (ADR: no rejection path), but a browser's normalised
        # user-agent is not an "agent" and exposing it is a fingerprint.
        # Fixed in the final existing-owner closure pass (owner Phase 13).
        payload["agent_signature"] = (
            None if r.actor_type == ActorType.HUMAN else signatures.get(r.ai_agent_id)
        )
        items.append(PageViewRead(**payload))
    return Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/page-views/with-ip", response_model=Page[PageViewReadWithIp])
def list_page_views_with_ip(
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> Page[PageViewReadWithIp]:
    """The full IP address, for OWNER and ADMIN only.

    A separate route rather than a flag on the route above: a permission
    that hides a field inside a shared handler is one refactor away from
    leaking it, and 'the field is only in this response model, and this
    model is only on this route' is checkable by reading two lines.
    """
    rows, total = telemetry_service.list_page_views(
        db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    signatures = telemetry_service.signatures_for(
        db, organization_id=current_user.organization_id,
        agent_ids=[r.ai_agent_id for r in rows],
    )
    items = []
    for r in rows:
        payload = PageViewReadWithIp.model_validate(r).model_dump()
        # A human visit carries no agent signature: every client gets a
        # registry row (ADR: no rejection path), but a browser's normalised
        # user-agent is not an "agent" and exposing it is a fingerprint.
        # Fixed in the final existing-owner closure pass (owner Phase 13).
        payload["agent_signature"] = (
            None if r.actor_type == ActorType.HUMAN else signatures.get(r.ai_agent_id)
        )
        items.append(PageViewReadWithIp(**payload))
    return Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/content-stats", response_model=Page[ContentViewStatRead])
def list_content_stats(
    date_from: date | None = None,
    date_to: date | None = None,
    content_type: str | None = None,
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ContentViewStatRead]:
    """"Which content was seen least / most, and how many times."

    Defaults to `total_views` descending. `sort_dir=asc` is the least-seen
    view, which is the more actionable half of the requirement: it is the
    list of pages nothing is reading.
    """
    rows, total = telemetry_service.list_content_stats(
        db,
        organization_id=current_user.organization_id,
        date_from=date_from,
        date_to=date_to,
        content_type=content_type,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    items = []
    for r in rows:
        payload = ContentViewStatRead.model_validate(r, from_attributes=True).model_dump()
        payload["mean_dwell_ms"] = r.mean_dwell_ms
        items.append(ContentViewStatRead(**payload))
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/content-stats/sortable-fields")
def content_stats_sortable_fields(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lets the dashboard build its sort control from the server's own
    allow-list instead of hard-coding a copy that can drift out of sync."""
    return {"fields": sorted(sortable_fields(ContentViewDaily))}


@router.post("/content-stats/recompute", status_code=status.HTTP_202_ACCEPTED)
def recompute_rollup(
    view_date: date,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    written = telemetry_service.rollup_day(
        db, organization_id=current_user.organization_id, view_date=view_date
    )
    db.commit()
    return {"view_date": view_date.isoformat(), "rows_written": written}


@router.get("/agents", response_model=Page[AiAgentRead])
def list_agents(
    actor_type: ActorType | None = None,
    origin: AgentRegistrationOrigin | None = None,
    seen_only: bool = False,
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AiAgentRead]:
    """Every automated client this organization has seen.

    There is no `known_only` filter and there never will be: filtering
    this list to recognised agents would hide precisely the rows the
    merchant needs to see.
    """
    rows, total = ai_agent_service.list_agents(
        db,
        organization_id=current_user.organization_id,
        actor_type=actor_type,
        origin=origin,
        seen_only=seen_only,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return Page(
        items=[AiAgentRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/agents/{agent_id}", response_model=AiAgentRead)
def rename_agent(
    agent_id: UUID,
    payload: AiAgentRename,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> AiAgentRead:
    agent = get_tenant_scoped_or_404(
        db, AiAgent, agent_id,
        organization_id=current_user.organization_id,
        not_found_message="Agent not found",
    )
    ai_agent_service.rename(db, agent=agent, display_name=payload.display_name)
    db.commit()
    db.refresh(agent)
    return AiAgentRead.model_validate(agent)


@router.get("/search-demand", response_model=Page[SearchDemandRead])
def list_search_demand(
    actor_type: ActorType | None = None,
    demand_source: SearchDemandSource | None = None,
    zero_results_only: bool = False,
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SearchDemandRead]:
    rows, total = search_demand_service.list_demand(
        db,
        organization_id=current_user.organization_id,
        actor_type=actor_type,
        demand_source=demand_source,
        zero_results_only=zero_results_only,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return Page(
        items=[SearchDemandRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search-demand/terms", response_model=Page[SearchTermAggregate])
def list_search_terms(
    actor_type: ActorType | None = None,
    zero_results_only: bool = False,
    ascending: bool = False,
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SearchTermAggregate]:
    """What people and machines are asking for, grouped by canonical Query.

    `actor_type=ai_crawler` answers "what are the bots looking for?";
    `zero_results_only=true` answers "what did we fail to answer?".
    """
    rows, total = search_demand_service.top_terms(
        db,
        organization_id=current_user.organization_id,
        actor_type=actor_type,
        zero_results_only=zero_results_only,
        ascending=ascending,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[SearchTermAggregate(**{**r, "query_status": str(getattr(r["query_status"], "value", r["query_status"]))}) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# Access policy — merchant decisions
# ===========================================================================


@router.get("/access-policies", response_model=Page[AccessPolicyRead])
def list_access_policies(
    limit: int = Q(default=50, ge=1, le=200),
    offset: int = Q(default=0, ge=0),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AccessPolicyRead]:
    rows, total = access_policy_service.list_policies(
        db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return Page(
        items=[AccessPolicyRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/access-policies", response_model=AccessPolicyRead)
def upsert_access_policy(
    payload: AccessPolicyWrite,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> AccessPolicyRead:
    """PUT, not POST: a rule is identified by its subject and purpose, not
    by a generated id, so writing it twice must produce one rule. A POST
    that created a second "GPTBot, training" row would make precedence
    ambiguous the moment it succeeded."""
    policy = access_policy_service.upsert_policy(
        db,
        organization_id=current_user.organization_id,
        agent_id=payload.agent_id,
        actor_type=payload.actor_type,
        purpose=payload.purpose,
        tier=payload.tier,
        reason=payload.reason,
        terms_url=payload.terms_url,
        updated_by_user_id=current_user.id,
    )
    db.commit()
    db.refresh(policy)
    return AccessPolicyRead.model_validate(policy)


@router.delete("/access-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_access_policy(
    policy_id: UUID,
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    policy = get_tenant_scoped_or_404(
        db, AccessPolicy, policy_id,
        organization_id=current_user.organization_id,
        not_found_message="Policy not found",
    )
    access_policy_service.delete_policy(db, policy=policy)
    db.commit()


# ===========================================================================
# Dashboard status strip
# ===========================================================================


@router.get("/health", response_model=TelemetryHealth)
def telemetry_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelemetryHealth:
    """Everything behind the dashboard's connection indicator.

    `overall` is the worst of its parts, never rounded up — the Phase 9
    `AIOL_Status` rule, restated here so the Cloud side cannot disagree
    with the plugin side about what "healthy" means.
    """
    from app.core.config import settings

    org_id = current_user.organization_id
    since = utcnow() - timedelta(hours=24)

    database_state = "ok"
    try:
        db.execute(select(func.count()).select_from(PageView).where(PageView.id.is_(None)))
    except Exception:  # noqa: BLE001
        database_state = "failed"

    recent = db.execute(
        select(func.count())
        .select_from(PageView)
        .where(PageView.organization_id == org_id, PageView.occurred_at >= since)
    ).scalar_one()
    last_event = db.execute(
        select(func.max(PageView.occurred_at)).where(PageView.organization_id == org_id)
    ).scalar_one()
    last_rollup = db.execute(
        select(func.max(ContentViewDaily.recomputed_at)).where(
            ContentViewDaily.organization_id == org_id
        )
    ).scalar_one()

    # Agents seen in traffic for which the merchant has made no decision.
    # Surfaced as a number precisely so "nobody decided" cannot stay
    # invisible and become de-facto policy.
    decided_agent_ids = select(AccessPolicy.agent_id).where(
        AccessPolicy.organization_id == org_id,
        AccessPolicy.agent_id.isnot(None),
        AccessPolicy.tier != AccessTier.UNSET,
    )
    awaiting = db.execute(
        select(func.count())
        .select_from(AiAgent)
        .where(
            AiAgent.organization_id == org_id,
            AiAgent.observation_count > 0,
            AiAgent.actor_type != ActorType.HUMAN,
            AiAgent.id.notin_(decided_agent_ids),
        )
    ).scalar_one()

    redis_state = "unknown"
    try:
        from app.security.rate_limit import redis_available

        redis_state = "ok" if redis_available() else "degraded"
    except Exception:  # noqa: BLE001
        # Honest: we could not determine it. Not "ok".
        redis_state = "unknown"

    states = [database_state, redis_state]
    if "failed" in states:
        overall = "failed"
    elif "degraded" in states or "unknown" in states:
        overall = "degraded"
    else:
        overall = "ok"

    return TelemetryHealth(
        core_reachable=True,
        database=database_state,
        redis=redis_state,
        rate_limiting="ok" if redis_state == "ok" else "degraded",
        overall=overall,
        api_version=TELEMETRY_API_VERSION,
        core_version=settings.CORE_VERSION,
        telemetry_events_last_24h=int(recent),
        last_event_at=last_event,
        last_rollup_at=last_rollup,
        agents_awaiting_decision=int(awaiting),
    )
