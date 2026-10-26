"""
`sync_jobs.document_id` (Step 7C-2, migration 0047).

Test 1 is fail-before / pass-after on the writer. Test 2 is a post-condition
check on the migration's own backfill statement (imported from the migration
file, never copied), run inside the rolled-back test session; CI also runs it
for real, on a fresh database, through `alembic upgrade head`.
"""

import importlib.util
import pathlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.models.enums import SyncJobStatus, SyncJobType
from app.models.sync_job import SyncJob
from app.services import ingestion_job_service

_MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0047_sync_jobs_document_id.py"
_spec = importlib.util.spec_from_file_location("migration_0047", _MIGRATION)
migration_0047 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration_0047)


def _document(client: TestClient, headers: dict) -> dict:
    def post(path: str, body: dict) -> dict:
        response = client.post(path, json=body, headers=headers)
        assert response.status_code in (200, 201), response.text
        return response.json()
    source = post("/api/v1/sources", {"source_type": "website", "title": "S"})
    return post(f"/api/v1/documents?source_id={source['id']}", {"title": "D", "content": "text"})


def test_a_new_ingestion_job_carries_its_document(client: TestClient, register_org, db_session) -> None:
    doc = _document(client, register_org()["headers"])
    job, created = ingestion_job_service.create_ingestion_job(
        db_session, organization_id=uuid.UUID(doc["organization_id"]), site_id=None,
        document_id=uuid.UUID(doc["id"]), conversion_id=uuid.uuid4(), source_hash="a" * 64, actor_user_id=None)

    stored = db_session.execute(select(SyncJob).where(SyncJob.id == job.id)).scalar_one()
    assert created
    assert stored.document_id == uuid.UUID(doc["id"])
    assert stored.payload["document_id"] == doc["id"]          # the payload copy stays


def test_backfill_fills_only_ingestion_jobs_whose_document_exists(client: TestClient, register_org, db_session) -> None:
    mine, theirs = _document(client, register_org()["headers"]), _document(client, register_org()["headers"])
    org = uuid.UUID(mine["organization_id"])

    def seed(document_id: str, job_type: SyncJobType = SyncJobType.DOCUMENT_INGESTION) -> SyncJob:
        job = SyncJob(organization_id=org, job_type=job_type, status=SyncJobStatus.SUCCEEDED,
                      payload={"document_id": document_id}, document_id=None)
        db_session.add(job)
        return job

    filled = seed(mine["id"])
    missing = seed(str(uuid.uuid4()))                          # its document is gone
    other_org = seed(theirs["id"])                             # a document of another organization
    other_type = seed(mine["id"], SyncJobType.CONTENT_MAPPING_SYNC)
    db_session.flush()

    first = db_session.execute(text(migration_0047.BACKFILL_SQL)).rowcount
    for job in (filled, missing, other_org, other_type):
        db_session.refresh(job)
    assert first >= 1
    assert filled.document_id == uuid.UUID(mine["id"])
    assert (missing.document_id, other_org.document_id, other_type.document_id) == (None, None, None)

    # Idempotent: a second run finds nothing left to fill and does not fail.
    assert db_session.execute(text(migration_0047.BACKFILL_SQL)).rowcount == 0
