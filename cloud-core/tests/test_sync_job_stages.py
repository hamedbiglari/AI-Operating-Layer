"""
`sync_job_stages` (Step 7C-3, migration 0048).

Test 1 is a post-condition on the migrated schema: conftest's create_all
would build the same table without 0048, so the migration's own proof is the
downgrade / upgrade round trip run outside pytest and CI's fresh-database
`alembic upgrade head`. Tests 2-4 check the constraints inside the rolled-back
test session.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.enums import SyncJobStageKey, SyncJobStageState, SyncJobStatus, SyncJobType
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage


def _organization(client: TestClient, register_org) -> uuid.UUID:
    response = client.get("/api/v1/organizations/me", headers=register_org()["headers"])
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


def _job(db, org: uuid.UUID) -> SyncJob:
    job = SyncJob(organization_id=org, job_type=SyncJobType.DOCUMENT_INGESTION, status=SyncJobStatus.RUNNING, payload={})
    db.add(job)
    db.flush()
    return job


def _stage(db, job: SyncJob, key: SyncJobStageKey, state: SyncJobStageState = SyncJobStageState.PENDING) -> SyncJobStage:
    stage = SyncJobStage(organization_id=job.organization_id, sync_job_id=job.id, stage_key=key, state=state)
    db.add(stage)
    db.flush()
    return stage


def test_migrated_schema(db_session) -> None:
    columns = {r[0]: (r[1], r[2]) for r in db_session.execute(text(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'sync_job_stages'"))}
    assert columns == {
        "id": ("uuid", "NO"), "organization_id": ("uuid", "NO"), "sync_job_id": ("uuid", "NO"),
        "stage_key": ("USER-DEFINED", "NO"), "state": ("USER-DEFINED", "NO"),
        "started_at": ("timestamp with time zone", "YES"), "completed_at": ("timestamp with time zone", "YES"),
        "detail": ("text", "YES"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    }
    labels = lambda t: [r[0] for r in db_session.execute(text(f"SELECT unnest(enum_range(NULL::{t}))::text"))]
    assert labels("sync_job_stage_key") == [k.value for k in SyncJobStageKey]
    assert labels("sync_job_stage_state") == [s.value for s in SyncJobStageState]
    unique = db_session.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_sync_job_stages_job_stage'")).scalar_one()
    assert unique == "UNIQUE (sync_job_id, stage_key)"
    indexes = {r[0] for r in db_session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'sync_job_stages'"))}
    assert {"ix_sync_job_stages_organization_id", "ix_sync_job_stages_sync_job_id"} <= indexes


def test_one_state_per_stage_per_job(client: TestClient, register_org, db_session) -> None:
    job = _job(db_session, _organization(client, register_org))
    _stage(db_session, job, SyncJobStageKey.UPLOAD)
    _stage(db_session, job, SyncJobStageKey.SECURITY)                  # another stage of the same job: fine
    with pytest.raises(IntegrityError), db_session.begin_nested():
        _stage(db_session, job, SyncJobStageKey.UPLOAD)                # the same stage again: rejected


def test_stage_rows_go_with_their_job(client: TestClient, register_org, db_session) -> None:
    job = _job(db_session, _organization(client, register_org))
    for key in (SyncJobStageKey.UPLOAD, SyncJobStageKey.CONVERSION):
        _stage(db_session, job, key)
    count = text("SELECT count(*) FROM sync_job_stages WHERE sync_job_id = :j")
    assert db_session.execute(count, {"j": job.id}).scalar_one() == 2
    db_session.execute(text("DELETE FROM sync_jobs WHERE id = :j"), {"j": job.id})
    assert db_session.execute(count, {"j": job.id}).scalar_one() == 0


def test_stage_values_and_round_trip(client: TestClient, register_org, db_session) -> None:
    job = _job(db_session, _organization(client, register_org))
    for key in SyncJobStageKey:                                        # all eight keys are accepted
        _stage(db_session, job, key)
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text(
            "INSERT INTO sync_job_stages (id, organization_id, sync_job_id, stage_key, state) "
            "VALUES (:id, :o, :j, 'translation', 'done')"), {"id": uuid.uuid4(), "o": job.organization_id, "j": job.id})

    other = _job(db_session, job.organization_id)
    started, completed = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc), datetime(2026, 10, 26, 9, 5, tzinfo=timezone.utc)
    row = SyncJobStage(organization_id=other.organization_id, sync_job_id=other.id, stage_key=SyncJobStageKey.OCR,
                       state=SyncJobStageState.DONE, started_at=started, completed_at=completed, detail="5 OCR blocks")
    db_session.add(row)
    db_session.flush()
    db_session.expire_all()
    back = db_session.execute(select(SyncJobStage).where(SyncJobStage.sync_job_id == other.id)).scalar_one()
    assert (back.organization_id, back.stage_key, back.state, back.started_at, back.completed_at, back.detail) == (
        other.organization_id, SyncJobStageKey.OCR, SyncJobStageState.DONE, started, completed, "5 OCR blocks")
