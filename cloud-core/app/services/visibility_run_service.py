"""
Visibility run execution (P12-18, ADR-074).

THE EXECUTION PATH

    create run (PENDING) -> enqueue SyncJob -> 202
                              worker -> reserve budget
                                     -> provider.probe() per query
                                     -> persist observation per query
                                     -> snapshot
                                     -> events vs previous snapshot
                                     -> settle budget

WHAT MAKES THIS HONEST RATHER THAN DECORATIVE

A provider failure produces an observation with `provider_outcome` set and
every signal NOT_CHECKED — not a missing row, and not an ABSENT finding.
The run then ends PARTIAL rather than SUCCEEDED, so a caller can see that
some queries were never measured. Dropping the row would make the failure
invisible; writing ABSENT would turn "we could not ask" into "the brand is
not there".
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    ProviderOutcome,
    SignalPresence,
    VisibilityEventType,
    VisibilityPlatform,
    VisibilityRunStatus,
    VisibilityTestType,
)
from app.models.query import Query
from app.models.visibility import VisibilityTest
from app.models.visibility_project import (
    VisibilityEvent,
    VisibilityProject,
    VisibilityRun,
    VisibilitySnapshot,
)
from app.security.tenant import get_tenant_scoped_or_404
from app.services import visibility_service
from app.services.audit import record_audit_log

SIGNALS = ("mentioned", "cited", "recommended", "product_present", "url_present")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_project_or_404(db: Session, *, project_id: UUID, organization_id: UUID) -> VisibilityProject:
    return get_tenant_scoped_or_404(
        db, VisibilityProject, project_id, organization_id=organization_id,
        not_found_message="Visibility project not found",
    )


def get_run_or_404(db: Session, *, run_id: UUID, organization_id: UUID) -> VisibilityRun:
    return get_tenant_scoped_or_404(
        db, VisibilityRun, run_id, organization_id=organization_id,
        not_found_message="Visibility run not found",
    )


def create_run(
    db: Session, *, organization_id: UUID, project_id: UUID, platform: VisibilityPlatform,
    provider_name: str, market: str | None = None, language: str | None = None,
    actor_user_id: UUID | None = None,
) -> VisibilityRun:
    """Creates the run row. No provider call happens here."""
    project = get_project_or_404(db, project_id=project_id, organization_id=organization_id)

    planned = db.execute(
        select(func.count()).select_from(Query).where(Query.organization_id == organization_id)
    ).scalar_one()

    run = VisibilityRun(
        organization_id=organization_id,
        project_id=project.id,
        platform=platform,
        market=market or (project.markets[0] if project.markets else None),
        language=language or (project.languages[0] if project.languages else None),
        provider_name=provider_name,
        methodology_version=project.methodology_version,
        status=VisibilityRunStatus.PENDING,
        queries_planned=planned,
    )
    db.add(run)
    db.flush()
    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="visibility_run.created", resource_type="visibility_run", resource_id=run.id,
        new_value={"project_id": str(project.id), "platform": platform.value,
                   "provider": provider_name},
    )
    return run


def execute_run(db: Session, *, run_id: UUID, query_limit: int = 50) -> dict:
    """Worker body. Never raises for an ordinary provider failure.

    Budget is reserved BEFORE each paid probe and settled after, reusing
    the Phase 12 atomic reservation (ADR-069) rather than a second system.
    """
    from app.integrations.visibility.fixture import get_provider

    run = db.get(VisibilityRun, run_id)
    if run is None:
        return {"status": "missing", "run_id": str(run_id)}
    if run.status in (VisibilityRunStatus.SUCCEEDED, VisibilityRunStatus.CANCELLED):
        return {"status": run.status.value, "run_id": str(run_id), "repeated": True}

    project = db.get(VisibilityProject, run.project_id)
    provider = get_provider(run.provider_name)

    run.status = VisibilityRunStatus.RUNNING
    run.started_at = _now()
    db.commit()

    queries = db.execute(
        select(Query).where(Query.organization_id == run.organization_id).limit(query_limit)
    ).scalars().all()

    observed = failed = 0
    for query in queries:
        estimate = provider.estimate_cost(platform=run.platform, prompt=query.query)
        if estimate is None:
            # Unknown cost must NOT be treated as free (§28). Refuse rather
            # than execute an unbounded charge.
            failed += 1
            _persist_observation(
                db, run=run, project=project, query=query,
                outcome=ProviderOutcome.AUTH_REQUIRED, provider=provider,
                error="Cost could not be determined; explicit authorization required",
            )
            continue
        try:
            visibility_service.reserve_budget(
                db, organization_id=run.organization_id, estimated_cost=estimate
            )
        except Exception:
            failed += 1
            _persist_observation(
                db, run=run, project=project, query=query,
                outcome=ProviderOutcome.UNAVAILABLE, provider=provider,
                error="Budget exhausted; no probe was performed",
            )
            continue

        probe_kwargs = dict(
            platform=run.platform, prompt=query.query, market=run.market,
            language=run.language,
            target_brand=project.target_brand if project else None,
            target_domain=project.target_domain if project else None,
        )
        if hasattr(provider, "probe_with_context"):
            # Phase 17: a model-backed provider runs through the shared AI
            # invocation wrapper, which records one AIExecution per provider
            # call under this run. budget_cleared is set only here, after
            # reserve_budget() above succeeded.
            from app.ai.invocation import InvocationContext
            from app.models.enums import AIParentType

            ctx = InvocationContext(
                organization_id=run.organization_id, parent_type=AIParentType.VISIBILITY_RUN,
                parent_id=run.id, stage="visibility_probe", budget_cleared=True,
            )
            result = provider.probe_with_context(db, ctx, **probe_kwargs)
        else:
            result = provider.probe(**probe_kwargs)
        # Settle to the real cost; a cheaper probe refunds the difference.
        visibility_service.settle_reservation(
            db, organization_id=run.organization_id, reserved=estimate,
            actual=(result.budget_settlement if getattr(result, "budget_settlement", None) is not None
                    else result.actual_cost if result.actual_cost is not None else estimate),
        )

        _persist_observation(db, run=run, project=project, query=query,
                             outcome=result.outcome, provider=provider, result=result)
        if result.usable:
            observed += 1
        else:
            failed += 1

    run.queries_observed = observed
    run.queries_failed = failed
    run.completed_at = _now()
    # PARTIAL is the honest status when some queries were never measured.
    if failed and observed:
        run.status = VisibilityRunStatus.PARTIAL
    elif failed and not observed:
        run.status = VisibilityRunStatus.FAILED
    else:
        run.status = VisibilityRunStatus.SUCCEEDED
    db.commit()

    snapshot = build_snapshot(db, run=run)
    events = detect_events(db, project_id=run.project_id,
                           organization_id=run.organization_id, snapshot=snapshot)
    return {
        "status": run.status.value, "run_id": str(run.id),
        "observed": observed, "failed": failed,
        "snapshot_id": str(snapshot.id) if snapshot else None,
        "events": len(events),
    }


def _persist_observation(
    db: Session, *, run: VisibilityRun, project, query, outcome: ProviderOutcome,
    provider, result=None, error: str | None = None,
) -> VisibilityTest:
    """Persists one observation, INCLUDING failures.

    A failed probe still produces a row: dropping it would make the failure
    invisible and quietly shrink the denominator, inflating every rate
    computed from the run."""
    signals = result.signals if result is not None else None
    observation = VisibilityTest(
        organization_id=run.organization_id,
        query_id=query.id,
        project_id=run.project_id,
        run_id=run.id,
        platform=run.platform,
        test_type=VisibilityTestType.DIRECT_QUERY,
        prompt=query.query,
        response=result.response_text if result else None,
        mentioned=signals.mentioned if signals else SignalPresence.NOT_CHECKED,
        cited=signals.cited if signals else SignalPresence.NOT_CHECKED,
        recommended=signals.recommended if signals else SignalPresence.NOT_CHECKED,
        product_present=signals.product_present if signals else SignalPresence.NOT_CHECKED,
        url_present=signals.url_present if signals else SignalPresence.NOT_CHECKED,
        platform_model=result.platform_model if result else None,
        provider_outcome=outcome.value,
        parser_version=result.parser_version if result else None,
        is_fixture=bool(result.is_fixture) if result else False,
        tested_at=_now(),
        estimated_cost=result.estimated_cost if result else None,
        ai_execution_id=getattr(result, "ai_execution_id", None) if result else None,
        result_metadata={"error": error or (result.error if result else None),
                         "provider": provider.name, "provider_version": provider.version},
    )
    db.add(observation)
    db.commit()
    return observation


def build_snapshot(db: Session, *, run: VisibilityRun) -> VisibilitySnapshot | None:
    """Immutable summary of one run.

    `observations_tested` counts only probes that actually succeeded. That
    is the denominator every rate must use; using `observations_total`
    instead would divide by queries nobody measured."""
    rows = db.execute(
        select(VisibilityTest).where(
            VisibilityTest.organization_id == run.organization_id,
            VisibilityTest.run_id == run.id,
        )
    ).scalars().all()
    if not rows:
        return None

    usable = [r for r in rows if r.provider_outcome in ("success", "partial")]
    snapshot = VisibilitySnapshot(
        organization_id=run.organization_id,
        project_id=run.project_id,
        run_id=run.id,
        platform=run.platform,
        market=run.market,
        language=run.language,
        observations_total=len(rows),
        observations_tested=len(usable),
        observations_failed=sum(1 for r in rows if r.provider_outcome == "failed"),
        observations_unavailable=sum(
            1 for r in rows
            if r.provider_outcome in ("unavailable", "rate_limited",
                                      "auth_required", "not_configured")
        ),
        mention_present=sum(1 for r in usable if r.mentioned == SignalPresence.PRESENT),
        citation_present=sum(1 for r in usable if r.cited == SignalPresence.PRESENT),
        recommendation_present=sum(1 for r in usable if r.recommended == SignalPresence.PRESENT),
        product_present=sum(1 for r in usable if r.product_present == SignalPresence.PRESENT),
        url_present=sum(1 for r in usable if r.url_present == SignalPresence.PRESENT),
        methodology_version=run.methodology_version,
        provider_name=run.provider_name,
        provider_version=run.provider_version,
        captured_at=_now(),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def detect_events(
    db: Session, *, project_id: UUID, organization_id: UUID, snapshot: VisibilitySnapshot | None
) -> list[VisibilityEvent]:
    """Compares a snapshot against the previous one for the same project
    and platform.

    Every event is descriptive. There is no causal field, because this
    system observes that a value changed and cannot know why."""
    if snapshot is None:
        return []

    previous = db.execute(
        select(VisibilitySnapshot).where(
            VisibilitySnapshot.organization_id == organization_id,
            VisibilitySnapshot.project_id == project_id,
            VisibilitySnapshot.platform == snapshot.platform,
            VisibilitySnapshot.id != snapshot.id,
        ).order_by(VisibilitySnapshot.captured_at.desc()).limit(1)
    ).scalars().first()

    events: list[VisibilityEvent] = []

    def add(event_type: VisibilityEventType, subject: str,
            before: int | None, after: int) -> None:
        events.append(VisibilityEvent(
            organization_id=organization_id, project_id=project_id,
            previous_snapshot_id=previous.id if previous else None,
            current_snapshot_id=snapshot.id, event_type=event_type,
            platform=snapshot.platform, subject=subject,
            previous_value=str(before) if before is not None else None,
            current_value=str(after), determination="observed",
            observed_at=snapshot.captured_at,
        ))

    if previous is None:
        add(VisibilityEventType.FIRST_OBSERVED, "project", None, snapshot.observations_tested)
    else:
        for field, event_type in (
            ("mention_present", VisibilityEventType.MENTION_CHANGED),
            ("citation_present", VisibilityEventType.CITATION_CHANGED),
            ("recommendation_present", VisibilityEventType.RECOMMENDATION_CHANGED),
        ):
            before, after = getattr(previous, field), getattr(snapshot, field)
            if before != after:
                add(event_type, field, before, after)

        if previous.product_present == 0 and snapshot.product_present > 0:
            add(VisibilityEventType.PRODUCT_APPEARED, "product_present",
                previous.product_present, snapshot.product_present)
        elif previous.product_present > 0 and snapshot.product_present == 0:
            add(VisibilityEventType.PRODUCT_DISAPPEARED, "product_present",
                previous.product_present, snapshot.product_present)

        if previous.url_present == 0 and snapshot.url_present > 0:
            add(VisibilityEventType.URL_APPEARED, "url_present",
                previous.url_present, snapshot.url_present)
        elif previous.url_present > 0 and snapshot.url_present == 0:
            add(VisibilityEventType.URL_DISAPPEARED, "url_present",
                previous.url_present, snapshot.url_present)

    for event in events:
        db.add(event)
    if events:
        db.commit()
    return events


def snapshot_rates(snapshot: VisibilitySnapshot) -> dict:
    """Sample-based rates, each WITH its denominator (§13).

    There is no overall score. Every rate is None when nothing was tested —
    not 0.0, which would assert a measured absence."""
    denominator = snapshot.observations_tested

    def rate(count: int) -> float | None:
        return round(count / denominator, 4) if denominator else None

    return {
        "denominator": denominator,
        "sample": {
            "observations_total": snapshot.observations_total,
            "observations_tested": denominator,
            "observations_failed": snapshot.observations_failed,
            "observations_unavailable": snapshot.observations_unavailable,
            "platform": snapshot.platform.value,
            "market": snapshot.market,
            "language": snapshot.language,
            "methodology_version": snapshot.methodology_version,
            "captured_at": snapshot.captured_at.isoformat(),
        },
        "ai_mention_rate": rate(snapshot.mention_present),
        "ai_citation_rate": rate(snapshot.citation_present),
        "ai_recommendation_share": rate(snapshot.recommendation_present),
        "ai_product_presence_rate": rate(snapshot.product_present),
        "caveat": (
            "Sample-based measurement over the monitored queries only. "
            "Not a market share and not a ranking; untested and failed "
            "observations are excluded from the denominator and reported "
            "separately."
        ),
    }
