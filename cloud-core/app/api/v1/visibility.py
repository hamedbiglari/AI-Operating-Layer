"""
AI Visibility endpoints (master spec §31).

What this surface deliberately does NOT offer:

  - no "visibility score", percentage or ranking (ADR-064)
  - no endpoint that performs a paid platform probe without a budget check
  - no way to record click or purchase, which this system cannot observe
    (ADR-062)

`GET /visibility/summary` returns counts with an explicit `caveats` list.
The caveats are not decoration: they state what the numbers do not cover,
which is the difference between a useful report and a misleading one.
"""

from datetime import datetime
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.workers.tasks import execute_visibility_run
from app.models.enums import (
    KNOWLEDGE_EDITOR_ROLES,
    CompetitorOrigin,
    SearchDataSource,
    VisibilityPlatform,
    VisibilityRunStatus,
)
from app.models.user import User
from app.models.visibility import VisibilityTest
from app.models.visibility_budget import VisibilityBudget
from app.models.search_observation import SearchObservation
from app.models.visibility_project import (
    VisibilityCompetitor,
    VisibilityEvent,
    VisibilityProject,
    VisibilityRun,
    VisibilitySnapshot,
)
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.visibility_infra import (
    SearchConsoleImportRequest,
    SearchImportResult,
    SearchObservationRead,
    SearchSummaryRead,
    SerpObserveRequest,
    VisibilityCompetitorCreate,
    VisibilityCompetitorRead,
    VisibilityEventRead,
    VisibilityProjectCreate,
    VisibilityProjectRead,
    VisibilityRatesRead,
    VisibilityRunAccepted,
    VisibilityRunCreate,
    VisibilityRunRead,
    VisibilitySnapshotRead,
)
from app.schemas.visibility import (
    VisibilityBudgetRead,
    VisibilityBudgetUpdate,
    VisibilityObservationCreate,
    VisibilityObservationRead,
    VisibilitySummary,
)
from app.security.dependencies import get_current_user, require_roles
from app.services import (
    search_intelligence_service,
    visibility_run_service,
    visibility_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visibility", tags=["visibility"])


@router.get("/observations", response_model=Page[VisibilityObservationRead])
def list_observations(
    platform: VisibilityPlatform | None = Query(default=None),
    query_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[VisibilityObservationRead]:
    items, total = visibility_service.list_observations(
        db, organization_id=current_user.organization_id, platform=platform,
        query_id=query_id, product_id=product_id,
        sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/observations", response_model=VisibilityObservationRead,
             status_code=status.HTTP_201_CREATED)
def record_observation(
    payload: VisibilityObservationCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> VisibilityTest:
    """Records one observation. Returns 402 if the estimated cost would
    exceed this period's budget — and in that case nothing is recorded and
    no probe is billed."""
    return visibility_service.record_observation(
        db, organization_id=current_user.organization_id,
        actor_user_id=current_user.id, **payload.model_dump(),
    )


@router.get("/observations/{observation_id}", response_model=VisibilityObservationRead)
def get_observation(
    observation_id: UUID, current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisibilityTest:
    return visibility_service.get_observation_or_404(
        db, observation_id=observation_id, organization_id=current_user.organization_id
    )


@router.get("/summary", response_model=VisibilitySummary)
def summary(
    platform: VisibilityPlatform | None = Query(default=None),
    since: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisibilitySummary:
    """Counts per signal, split present / absent / not_checked, plus
    caveats stating what is not covered. No score, by design."""
    return VisibilitySummary(
        **visibility_service.summarise(
            db, organization_id=current_user.organization_id, platform=platform, since=since
        )
    )


@router.get("/budget", response_model=VisibilityBudgetRead)
def get_budget(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VisibilityBudget:
    """A missing budget is created with a limit of ZERO — "not configured"
    and "unlimited" must never be the same state."""
    return visibility_service.get_or_create_budget(
        db, organization_id=current_user.organization_id
    )


@router.put("/budget", response_model=VisibilityBudgetRead)
def set_budget(
    payload: VisibilityBudgetUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> VisibilityBudget:
    return visibility_service.set_budget(
        db, organization_id=current_user.organization_id,
        period_limit=payload.period_limit, currency=payload.currency,
        actor_user_id=current_user.id,
    )


# =========================================================================
# P12-18 Visibility infrastructure / P12-19 Search intelligence
# (ADR-074, ADR-075)
#
# Runs are ASYNC: the route creates the run and returns 202. Probing N
# queries against an external provider inside an HTTP request is exactly
# the shape of work that times out and leaves no record.
# =========================================================================


@router.post("/projects", response_model=VisibilityProjectRead,
             status_code=status.HTTP_201_CREATED)
def create_project(
    payload: VisibilityProjectCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> VisibilityProject:
    project = VisibilityProject(
        organization_id=current_user.organization_id,
        site_id=payload.site_id,
        name=payload.name,
        description=payload.description,
        markets=payload.markets,
        languages=payload.languages,
        platforms=[p.value for p in payload.platforms],
        target_brand=payload.target_brand,
        target_domain=payload.target_domain,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=Page[VisibilityProjectRead])
def list_projects(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[VisibilityProjectRead]:
    from app.schemas.common import SortDirection, apply_sort

    base = select(VisibilityProject).where(
        VisibilityProject.organization_id == current_user.organization_id
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(
        apply_sort(base, VisibilityProject, sort, "created_at", SortDirection.DESC)
        .limit(pagination.limit).offset(pagination.offset)
    ).scalars().all()
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/projects/{project_id}/runs", response_model=VisibilityRunAccepted,
             status_code=status.HTTP_202_ACCEPTED)
def create_run(
    project_id: UUID,
    payload: VisibilityRunCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> VisibilityRunAccepted:
    """Creates a run and queues it. Returns 202 — no provider is called
    here (P12-18 §9)."""
    run = visibility_run_service.create_run(
        db, organization_id=current_user.organization_id, project_id=project_id,
        platform=payload.platform, provider_name=payload.provider_name,
        market=payload.market, language=payload.language,
        actor_user_id=current_user.id,
    )
    run.status = VisibilityRunStatus.QUEUED
    db.commit()
    db.refresh(run)

    try:
        execute_visibility_run.delay(str(run.id))
    except Exception as exc:  # broker unavailable
        logger.warning("visibility run enqueue failed for %s: %s", run.id, exc)

    return VisibilityRunAccepted(
        run_id=run.id, status=run.status, job_id=run.sync_job_id,
        status_url=f"/api/v1/visibility/runs/{run.id}",
    )


@router.get("/runs/{run_id}", response_model=VisibilityRunRead)
def get_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisibilityRun:
    return visibility_run_service.get_run_or_404(
        db, run_id=run_id, organization_id=current_user.organization_id
    )


@router.get("/projects/{project_id}/snapshots", response_model=Page[VisibilitySnapshotRead])
def list_snapshots(
    project_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[VisibilitySnapshotRead]:
    from app.schemas.common import SortDirection, apply_sort

    visibility_run_service.get_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    base = select(VisibilitySnapshot).where(
        VisibilitySnapshot.organization_id == current_user.organization_id,
        VisibilitySnapshot.project_id == project_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(
        apply_sort(base, VisibilitySnapshot, sort, "captured_at", SortDirection.DESC)
        .limit(pagination.limit).offset(pagination.offset)
    ).scalars().all()
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/snapshots/{snapshot_id}/rates", response_model=VisibilityRatesRead)
def snapshot_rates(
    snapshot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisibilityRatesRead:
    """Sample-based rates WITH denominators. No overall score exists."""
    snapshot = db.execute(
        select(VisibilitySnapshot).where(
            VisibilitySnapshot.id == snapshot_id,
            VisibilitySnapshot.organization_id == current_user.organization_id,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return VisibilityRatesRead(**visibility_run_service.snapshot_rates(snapshot))


@router.get("/projects/{project_id}/events", response_model=Page[VisibilityEventRead])
def list_events(
    project_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[VisibilityEventRead]:
    from app.schemas.common import SortDirection, apply_sort

    visibility_run_service.get_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    base = select(VisibilityEvent).where(
        VisibilityEvent.organization_id == current_user.organization_id,
        VisibilityEvent.project_id == project_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(
        apply_sort(base, VisibilityEvent, sort, "observed_at", SortDirection.DESC)
        .limit(pagination.limit).offset(pagination.offset)
    ).scalars().all()
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/projects/{project_id}/competitors", response_model=VisibilityCompetitorRead,
             status_code=status.HTTP_201_CREATED)
def add_competitor(
    project_id: UUID,
    payload: VisibilityCompetitorCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> VisibilityCompetitor:
    """A SYSTEM_DISCOVERED competitor is NOT approved on creation — only a
    merchant-defined one is. Declaring a brand a competitor without
    approval puts words in the merchant's mouth."""
    visibility_run_service.get_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    competitor = VisibilityCompetitor(
        organization_id=current_user.organization_id,
        project_id=project_id,
        name=payload.name,
        domain=payload.domain,
        origin=payload.origin,
        is_approved=(payload.origin == CompetitorOrigin.MERCHANT_DEFINED),
        notes=payload.notes,
    )
    db.add(competitor)
    db.commit()
    db.refresh(competitor)
    return competitor


@router.get("/projects/{project_id}/competitors", response_model=Page[VisibilityCompetitorRead])
def list_competitors(
    project_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[VisibilityCompetitorRead]:
    from app.schemas.common import SortDirection, apply_sort

    visibility_run_service.get_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    base = select(VisibilityCompetitor).where(
        VisibilityCompetitor.organization_id == current_user.organization_id,
        VisibilityCompetitor.project_id == project_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(
        apply_sort(base, VisibilityCompetitor, sort, "created_at", SortDirection.DESC)
        .limit(pagination.limit).offset(pagination.offset)
    ).scalars().all()
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# --- P12-19 Search intelligence ------------------------------------------------


@router.post("/search/console/import", response_model=SearchImportResult)
def import_search_console(
    payload: SearchConsoleImportRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> SearchImportResult:
    """Imports through the Search Console boundary.

    A provider failure returns `data_retrieved: false` with the outcome,
    never zero rows — "could not connect" and "no impressions" are
    different facts."""
    result = search_intelligence_service.import_search_console(
        db, organization_id=current_user.organization_id,
        property_url=payload.property_url, start_date=payload.start_date,
        end_date=payload.end_date, provider_name=payload.provider_name,
        market=payload.market, actor_user_id=current_user.id,
    )
    return SearchImportResult(**result)


@router.post("/search/serp/observe", response_model=SearchImportResult)
def observe_serp(
    payload: SerpObserveRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> SearchImportResult:
    try:
        result = search_intelligence_service.observe_serp(
            db, organization_id=current_user.organization_id,
            query_text=payload.query, surface=payload.surface, market=payload.market,
            language=payload.language, depth=payload.depth,
            provider_name=payload.provider_name, actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    return SearchImportResult(**result)


@router.get("/search/observations", response_model=Page[SearchObservationRead])
def list_search_observations(
    data_source: SearchDataSource | None = Query(default=None),
    market: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SearchObservationRead]:
    from app.schemas.common import SortDirection, apply_sort

    base = select(SearchObservation).where(
        SearchObservation.organization_id == current_user.organization_id
    )
    if data_source:
        base = base.where(SearchObservation.data_source == data_source)
    if market:
        base = base.where(SearchObservation.market == market)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(
        apply_sort(base, SearchObservation, sort, "observed_date", SortDirection.DESC)
        .limit(pagination.limit).offset(pagination.offset)
    ).scalars().all()
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/search/summary", response_model=SearchSummaryRead)
def search_summary(
    data_source: SearchDataSource | None = Query(default=None),
    market: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchSummaryRead:
    return SearchSummaryRead(
        **search_intelligence_service.summarise(
            db, organization_id=current_user.organization_id,
            data_source=data_source, market=market,
        )
    )
