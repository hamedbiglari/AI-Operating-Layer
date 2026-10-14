"""
Asynchronous document ingestion jobs (P12-02, P12-03; ADR-071).

WHY THE UPLOAD ENDPOINT MUST NOT DO THE WORK

Conversion, table extraction and OCR are unbounded in a way HTTP is not: a
200-page scanned PDF can occupy a worker for minutes. Doing that inside the
request means the client's timeout decides whether the document is ingested,
and a retry starts the whole thing again. So the endpoint persists the
original, records a job, enqueues it, and returns 202 with a durable id.

REUSES THE CANONICAL JOB MODEL

`SyncJob` (Phase 10) with `job_type=DOCUMENT_INGESTION`. A second job system
would be the duplicate domain ADR-068 just removed.

FAILURE RECOVERY (P12-03)

    QUEUED -> RUNNING -> SUCCEEDED
                      -> RETRYING -> RUNNING -> ...
                      -> FAILED            (attempts exhausted)

`RETRYING` is distinct from `FAILED`: it says a retry is scheduled, so an
operator can tell work that is still moving from work that has stopped.

**A job stuck in RUNNING is detectable.** `started_at` plus a lease horizon
makes a crashed worker's job reclaimable — without it, a worker killed
mid-conversion leaves a row that looks busy forever and nothing ever
notices.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import SyncJobStatus, SyncJobType
from app.models.sync_job import SyncJob
from app.services.audit import record_audit_log

MAX_ATTEMPTS = 3
# A RUNNING job older than this is presumed abandoned by a dead worker.
# Generous relative to conversion time so a slow-but-alive job is not
# reclaimed out from under itself.
LEASE_SECONDS = 900


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_ingestion_job(
    db: Session, *, organization_id: UUID, site_id: UUID | None, document_id: UUID,
    conversion_id: UUID, source_hash: str, actor_user_id: UUID | None,
    idempotency_key: str | None = None, ocr_languages: str = "eng",
    enable_ocr: bool = True,
) -> tuple[SyncJob, bool]:
    """Returns (job, created).

    The default idempotency key is `ingest:<org>:<source_hash>`, so the same
    bytes uploaded twice reuse one job rather than queueing duplicate
    conversion work (P12-04). A caller wanting deliberate reprocessing
    passes its own key."""
    key = idempotency_key or f"ingest:{organization_id}:{source_hash}"

    existing = db.execute(
        select(SyncJob).where(
            SyncJob.organization_id == organization_id,
            SyncJob.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    job = SyncJob(
        organization_id=organization_id,
        site_id=site_id,
        job_type=SyncJobType.DOCUMENT_INGESTION,
        status=SyncJobStatus.QUEUED,
        payload={
            "document_id": str(document_id),
            "conversion_id": str(conversion_id),
            "source_hash": source_hash,
            "ocr_languages": ocr_languages,
            "enable_ocr": enable_ocr,
        },
        idempotency_key=key,
    )
    db.add(job)
    db.flush()
    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="document_ingestion.queued", resource_type="sync_job", resource_id=job.id,
        new_value={"document_id": str(document_id)},
    )
    db.commit()
    db.refresh(job)
    return job, True


def claim(db: Session, *, job_id: UUID) -> SyncJob | None:
    """Marks a job RUNNING and increments attempts.

    Returns None if the job is already terminal, so a duplicate queue
    delivery cannot re-run finished work."""
    job = db.get(SyncJob, job_id)
    if job is None:
        return None
    if job.status in (SyncJobStatus.SUCCEEDED, SyncJobStatus.CANCELLED):
        return None
    job.status = SyncJobStatus.RUNNING
    job.attempts += 1
    job.started_at = _now()
    db.commit()
    db.refresh(job)
    return job


def succeed(db: Session, *, job: SyncJob, result: dict | None = None) -> SyncJob:
    job.status = SyncJobStatus.SUCCEEDED
    job.completed_at = _now()
    job.error_message = None
    if result:
        payload = dict(job.payload or {})
        payload["result"] = result
        job.payload = payload
    db.commit()
    db.refresh(job)
    return job


def fail(db: Session, *, job: SyncJob, error: str, retryable: bool = True) -> SyncJob:
    """RETRYING while attempts remain and the error is retryable; otherwise
    FAILED.

    A permanent error (unsupported format, malformed file) is NOT retried:
    re-running the same converter over the same bytes cannot produce a
    different outcome, and pretending otherwise burns three attempts before
    telling the operator something they could have known immediately."""
    job.error_message = error[:1000]
    if retryable and job.attempts < MAX_ATTEMPTS:
        job.status = SyncJobStatus.RETRYING
        job.completed_at = None
    else:
        job.status = SyncJobStatus.FAILED
        job.completed_at = _now()
    db.commit()
    db.refresh(job)
    return job


def reclaim_stalled(db: Session, *, organization_id: UUID | None = None) -> list[SyncJob]:
    """Finds RUNNING jobs whose lease has expired and moves them on.

    This is what makes "no job silently stays RUNNING forever" true rather
    than aspirational. A worker killed mid-conversion leaves a RUNNING row
    that nothing would otherwise revisit."""
    horizon = _now() - timedelta(seconds=LEASE_SECONDS)
    query = select(SyncJob).where(
        SyncJob.job_type == SyncJobType.DOCUMENT_INGESTION,
        SyncJob.status == SyncJobStatus.RUNNING,
        SyncJob.started_at.is_not(None),
        SyncJob.started_at < horizon,
    )
    if organization_id:
        query = query.where(SyncJob.organization_id == organization_id)

    reclaimed: list[SyncJob] = []
    for job in db.execute(query).scalars().all():
        fail(db, job=job, error="Worker lease expired; job presumed abandoned.", retryable=True)
        reclaimed.append(job)
    return reclaimed


def get_job(db: Session, *, job_id: UUID, organization_id: UUID) -> SyncJob | None:
    return db.execute(
        select(SyncJob).where(
            SyncJob.id == job_id, SyncJob.organization_id == organization_id
        )
    ).scalar_one_or_none()


# P14-CORRECTION-001 (Phase 15): manual retry. Model A — same job_id,
# attempts keeps counting from wherever automatic retry left off; no new
# job row. This is the only model consistent with the existing schema
# (SyncJob.attempts, MAX_ATTEMPTS, the QUEUED->RUNNING->...->FAILED state
# machine already documented at the top of this file) — a second job row
# per retry would fork job history and break the 1:1 idempotency_key
# relationship the rest of this file depends on. See
# docs/phase15/ADR-MANUAL-RETRY.md.
RETRY_ELIGIBLE_STATES = (SyncJobStatus.FAILED, SyncJobStatus.DEAD_LETTER)


class RetryNotEligible(Exception):
    """Raised when the job is not in a state that can be retried."""

    def __init__(self, current_status: SyncJobStatus) -> None:
        self.current_status = current_status
        super().__init__(f"job is {current_status.value}, not retryable")


def retry_job(
    db: Session, *, job_id: UUID, organization_id: UUID, actor_user_id: UUID | None
) -> tuple[SyncJob, bool]:
    """Manually retry a failed job. Returns (job, dispatched).

    Tenant ownership is enforced by `get_job` itself (organization_id is
    part of the WHERE clause, not a post-hoc check) — a job belonging to
    another tenant is indistinguishable from a job that does not exist,
    which is what the caller (a 404) should see.

    Idempotency: only a job in RETRY_ELIGIBLE_STATES is transitioned and
    (re-)dispatched. A second, third, Nth call against a job that has
    already moved to QUEUED/RUNNING/RETRYING/SUCCEEDED by the first call
    returns `dispatched=False` and the job as it currently stands —
    it does not re-enqueue a second Celery execution. This is the same
    guarantee `create_url_ingestion_job`'s idempotency_key gives the
    initial submission, applied to the retry action itself.
    """
    job = get_job(db, job_id=job_id, organization_id=organization_id)
    if job is None:
        return None, False  # caller maps this to 404

    if job.status not in RETRY_ELIGIBLE_STATES:
        raise RetryNotEligible(job.status)

    job.status = SyncJobStatus.QUEUED
    # error_message is deliberately NOT cleared here: the mandate requires
    # the dashboard to keep showing "original failure" alongside the retry
    # in progress. It is overwritten naturally by the next real outcome —
    # succeed() on success, fail() with the new error text if it fails
    # again — never blanked out just because a retry was requested.
    job.started_at = None
    job.completed_at = None
    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="ingestion_job.manual_retry", resource_type="sync_job",
        resource_id=job.id, new_value={"attempts_before_retry": job.attempts},
    )
    db.commit()
    db.refresh(job)
    return job, True


def run_ingestion_job(
    db: Session, *, job_id: UUID, organization_id: UUID | None = None
) -> dict:
    """The ingestion job body, as a plain function taking a session.

    The Celery task is a thin wrapper around this. Separating them matters
    for more than tidiness: a task that opens its own session cannot be
    driven by a caller that already has one, which makes the real chain
    untestable without a live broker and a committed database. Keeping the
    body session-agnostic lets tests exercise the actual transitions and
    persistence.

    Returns a result dict; never raises for expected failures, because the
    caller's job is to record the outcome, not to distinguish exceptions.
    """
    from app.ingestion.converter import ConversionStatus
    from app.services import ingestion_service

    if organization_id is not None:
        # An explicit tenant assertion. The worker itself does not need it
        # (the job row carries its own organization), but a caller that
        # knows the tenant should be able to state it - and a mismatch then
        # becomes a refusal rather than silent cross-tenant execution.
        scoped = get_job(db, job_id=job_id, organization_id=organization_id)
        if scoped is None:
            return {"status": "skipped", "reason": "job not found for this organization"}

    job = claim(db, job_id=job_id)
    if job is None:
        return {"status": "skipped", "reason": "job already terminal or missing"}

    payload = job.payload or {}
    try:
        if payload.get("kind") == "url":
            # URL-kind jobs (POST /documents/ingest-url) never had a
            # document_id at creation time — the whole point is that
            # fetching the URL is what CREATES the document. This branch
            # was missing entirely: every url-kind job fell through to the
            # document_id/conversion_id path below and failed immediately
            # with KeyError('document_id'), retried twice per the task's
            # own retry policy, then failed permanently — confirmed by
            # actually running one end to end against a real worker
            # (Phase 14 forensic pass). fetch_and_ingest_url already
            # existed, fully implemented, just never called from here.
            from app.ingestion.url_source import UrlRejected
            from app.services.url_ingestion_service import fetch_and_ingest_url

            try:
                outcome = fetch_and_ingest_url(
                    db,
                    organization_id=job.organization_id,
                    source_id=UUID(payload["source_id"]),
                    url=payload["url"],
                    title=payload.get("title"),
                    language=payload.get("language", "en"),
                )
            except UrlRejected as exc:
                # Permanent, not retryable: a blocked target is blocked
                # identically on every retry (see fetch_and_ingest_url's
                # own docstring) — retrying would turn a policy rejection
                # into a slow internal port scan.
                fail(db, job=job, error=f"UrlRejected: {exc}", retryable=False)
                return {"status": "error", "error": f"UrlRejected: {exc}"}
        else:
            outcome = ingestion_service.process_pending_conversion(
                db,
                organization_id=job.organization_id,
                document_id=UUID(payload["document_id"]),
                conversion_id=UUID(payload["conversion_id"]),
                enable_ocr=bool(payload.get("enable_ocr", True)),
                ocr_languages=str(payload.get("ocr_languages", "eng")),
            )
    except Exception as exc:  # noqa: BLE001
        # Unexpected exceptions are treated as transient: the bytes are
        # retained, so a retry is cheap and may well succeed.
        fail(db, job=job, error=f"{type(exc).__name__}: {exc}", retryable=True)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    permanent = {
        ConversionStatus.UNSUPPORTED.value,
        ConversionStatus.FAILED.value,
        ConversionStatus.EMPTY.value,
    }
    if outcome["conversion_status"] in permanent:
        # THE JOB SUCCEEDED; THE CONVERSION DID NOT. Those are different
        # facts and collapsing them loses information in both directions:
        #
        #   - marking the job FAILED invites an operator to retry work that
        #     cannot succeed (the same converter over the same bytes gives
        #     the same answer), and
        #   - it hides that the pipeline is healthy and did exactly what it
        #     was asked to do.
        #
        # The verdict lives in `conversion_status`, which is where a caller
        # asking "can this document be used?" should look. Job FAILED is
        # reserved for execution failures - exceptions, timeouts, a dead
        # worker - where a retry genuinely might help.
        succeed(db, job=job, result=outcome)
        return {"status": "succeeded", **outcome}

    succeed(db, job=job, result=outcome)
    return {"status": "succeeded", **outcome}
