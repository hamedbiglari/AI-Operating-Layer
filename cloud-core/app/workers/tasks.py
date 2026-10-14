"""
Celery task definitions.

`execute_research_task_job` is a thin wrapper: it opens its own DB
session (a Celery worker is a separate process with no FastAPI request
to hang a `get_db` dependency off of, so it uses `SessionLocal`
directly — the same session factory `get_db` itself uses) and delegates
the actual work to `research_task_service.execute_research_task`, which
has no Celery dependency of its own and is exercised directly by tests
(see tests/test_research_execution.py) without needing a broker or
worker process at all.
"""

from uuid import UUID

from app.db.session import SessionLocal
from app.workers.celery_app import celery_app


@celery_app.task(name="research.execute_task")
def execute_research_task_job(task_id: str, organization_id: str) -> None:
    from app.services.research_task_service import execute_research_task

    db = SessionLocal()
    try:
        execute_research_task(
            db,
            task_id=UUID(task_id),
            organization_id=UUID(organization_id),
            actor_user_id=None,
        )
    finally:
        db.close()


@celery_app.task(
    name="documents.ingest",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def ingest_document_job(self, job_id: str) -> dict:  # noqa: ANN001
    """Thin Celery wrapper over `ingestion_job_service.run_ingestion_job`.

    The body lives in the service, not here, so the real chain is testable
    without a live broker: a task that owns its session cannot be driven by
    a caller that already has one. This wrapper adds exactly two things —
    a database session and Celery's retry scheduling.
    """
    from uuid import UUID

    from app.db.session import SessionLocal
    from app.models.enums import SyncJobStatus
    from app.models.sync_job import SyncJob
    from app.services import ingestion_job_service

    with SessionLocal() as db:
        result = ingestion_job_service.run_ingestion_job(db, job_id=UUID(job_id))

        # Re-read the state the service recorded; RETRYING means it wants
        # another attempt, which only Celery can schedule.
        job = db.get(SyncJob, UUID(job_id))
        if job is not None and job.status == SyncJobStatus.RETRYING:
            raise self.retry(exc=RuntimeError(job.error_message or "ingestion retry"))
        return result


@celery_app.task(name="documents.reclaim_stalled")
def reclaim_stalled_ingestions(older_than_seconds: int = 900) -> dict:
    """Periodic sweep so a job cannot sit in RUNNING forever (P12-03)."""
    from app.db.session import SessionLocal
    from app.services import ingestion_jobs

    with SessionLocal() as db:
        reclaimed = ingestion_jobs.reclaim_stalled_jobs(
            db, older_than_seconds=older_than_seconds
        )
        return {"reclaimed": [str(j.id) for j in reclaimed]}


@celery_app.task(name="visibility.execute_run", bind=True, max_retries=2, default_retry_delay=5)
def execute_visibility_run(self, run_id: str) -> dict:  # noqa: ANN001
    """Thin wrapper over `visibility_run_service.execute_run` (P12-18 §9).

    The body lives in the service so the real chain is testable without a
    live broker — the same separation that made the ingestion path
    verifiable (ADR-073).
    """
    from uuid import UUID

    from app.db.session import SessionLocal
    from app.services import visibility_run_service

    with SessionLocal() as db:
        return visibility_run_service.execute_run(db, run_id=UUID(run_id))


@celery_app.task(name="ai_executions.reclaim_stale")
def reclaim_stale_ai_executions(older_than_seconds: int | None = None) -> dict:
    """Phase 17: RUNNING executions whose worker died become ABANDONED
    (outcome and cost unknown) — never SUCCEEDED, never a fabricated result."""
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.services import ai_execution_service

    db = SessionLocal()
    try:
        count = ai_execution_service.reclaim_stale_executions(
            db, older_than_seconds=older_than_seconds or settings.AI_EXECUTION_STALE_SECONDS)
        return {"reclaimed": count}
    finally:
        db.close()


@celery_app.task(name="background.policy_check")
def check_task_eligibility(organization_id: str, task_type: str) -> dict:
    """Standalone check: returns whether a tenant's policy allows a task type.
    Workers that process background tasks MUST call this before selecting any resource.
    Returning allowed=False means no connected account may be used."""
    from uuid import UUID
    from app.services.background_policy_service import check_background_policy
    db = SessionLocal()
    try:
        decision = check_background_policy(db, organization_id=UUID(organization_id), task_type=task_type)
        return {"allowed": decision.allowed, "reason": decision.reason,
                "allowed_account_ids": [str(i) for i in decision.allowed_account_ids],
                "routing_mode": decision.routing_mode, "max_cost_per_run": decision.max_cost_per_run}
    finally:
        db.close()


@celery_app.task(name="ai_center.run_job")
def run_ai_job(job_id: str) -> dict:
    """AI Center: process an AI job's pending items with checkpoint/handoff switching."""
    from uuid import UUID

    from app.db.session import SessionLocal
    from app.models.ai_center import AIJob
    from app.services import ai_job_service

    db = SessionLocal()
    try:
        job = db.get(AIJob, UUID(job_id))
        if job is None or job.status not in ("queued", "paused", "blocked"):
            return {"skipped": True}
        return ai_job_service.run_job(db, job)
    finally:
        db.close()
