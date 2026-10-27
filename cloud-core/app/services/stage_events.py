"""
Stage events for document-ingestion jobs (Step 7C-4): the writes behind
sync_job_stages, gated by AIOL_EMIT_STAGE_EVENTS (default off).

With the flag off every function here returns before touching the session,
so ingestion behaves exactly as it did before 7C-4.

Upload and security run inside the upload request, before the job exists. A
job is only created once both have passed (a failed check is an HTTP error and
no job), so their rows are written as done when the job is created (D15).
Conversion, structure and OCR run as one pipeline call and move together
(D16, D17); chunking, evidence and knowledge have no job and get no rows here.

None of these functions commits: each shares the caller's commit.
"""

import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models.enums import SyncJobStageKey, SyncJobStageState
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage

RECEIVED = (SyncJobStageKey.UPLOAD, SyncJobStageKey.SECURITY)
RUN = (SyncJobStageKey.CONVERSION, SyncJobStageKey.STRUCTURE, SyncJobStageKey.OCR)


def enabled() -> bool:
    return os.getenv("AIOL_EMIT_STAGE_EVENTS", "false").lower() in ("1", "true", "yes")


def record_received(db: Session, *, job: SyncJob) -> None:
    """Upload and security, done as of the job's creation (D15)."""
    if not enabled():
        return
    for key in RECEIVED:
        db.add(SyncJobStage(organization_id=job.organization_id, sync_job_id=job.id, stage_key=key,
                            state=SyncJobStageState.DONE, started_at=job.created_at,
                            completed_at=job.created_at))


def reset_run(db: Session, *, job_id: UUID) -> None:
    """Clears an earlier attempt's run rows, so a retry of the same job starts clean (D16)."""
    if not enabled():
        return
    db.execute(delete(SyncJobStage).where(SyncJobStage.sync_job_id == job_id,
                                          SyncJobStage.stage_key.in_(RUN)))


def start_run(db: Session, *, job_id: UUID, organization_id: UUID) -> None:
    if not enabled():
        return
    now = datetime.now(timezone.utc)
    for key in RUN:
        db.add(SyncJobStage(organization_id=organization_id, sync_job_id=job_id, stage_key=key,
                            state=SyncJobStageState.ACTIVE, started_at=now))


def format_count(n: int | None, singular: str, plural: str) -> str:
    """"1 table" / "N tables": shared with processing_service's derived details (D22)."""
    n = n or 0
    return f"{n} {singular}" if n == 1 else f"{n} {plural}"


def finish_run(db: Session, *, job_id: UUID, conversion_status: str, conversion_error: str | None,
               table_count: int | None, ocr_block_count: int | None) -> None:
    """One completed_at for all three: they finish in the same pipeline call (D17).

    A conversion that failed or was unsupported stops the pipeline before the
    structure pass (pipeline.py), so structure and OCR are recorded as not run
    rather than done. An empty conversion still ran both; it found no text."""
    if not enabled():
        return
    now = datetime.now(timezone.utc)
    done = {"state": SyncJobStageState.DONE, "completed_at": now}
    not_run = {"state": SyncJobStageState.NOT_TRACKED, "started_at": None, "completed_at": None,
               "detail": "not run (conversion failed)"}
    structure = {**done, "detail": format_count(table_count, "table", "tables")}
    ocr = {**done, "detail": format_count(ocr_block_count, "OCR block", "OCR blocks")}
    if conversion_status in ("failed", "unsupported"):
        conversion = {**done, "state": SyncJobStageState.FAILED, "detail": conversion_error or "conversion failed"}
        structure = ocr = not_run
    elif conversion_status == "empty":
        conversion = {**done, "state": SyncJobStageState.FAILED, "detail": "no usable text"}
    else:
        conversion = {**done, "detail": None}
    for key, values in ((SyncJobStageKey.CONVERSION, conversion), (SyncJobStageKey.STRUCTURE, structure),
                        (SyncJobStageKey.OCR, ocr)):
        db.execute(update(SyncJobStage)
                   .where(SyncJobStage.sync_job_id == job_id, SyncJobStage.stage_key == key)
                   .values(**values))


def fail_active(db: Session, *, job_id: UUID, error: str) -> None:
    """Whatever was still running when the job failed is marked failed (D16)."""
    if not enabled():
        return
    db.execute(update(SyncJobStage)
               .where(SyncJobStage.sync_job_id == job_id, SyncJobStage.state == SyncJobStageState.ACTIVE)
               .values(state=SyncJobStageState.FAILED, completed_at=datetime.now(timezone.utc),
                       detail=error[:1000]))
