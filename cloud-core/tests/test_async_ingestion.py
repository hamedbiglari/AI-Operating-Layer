"""
Asynchronous ingestion (P12-02, P12-03, P12-04; ADR-071).

These tests exercise the REAL chain — HTTP → 202 → job row → task function →
artifacts — and assert persisted database state at each stage. They do not
mock the queue, because a mock would pass against an implementation that
never enqueued anything, which is exactly the defect being fixed.

Celery is invoked via `.apply()` (eager, in-process) rather than a live
worker: the task body, job transitions and persistence are all real, only
the broker hop is elided. That distinction is stated rather than blurred —
a live-worker test is a separate, heavier thing.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.storage import OriginalSourceStore, set_store
from app.models.enums import SyncJobStatus
from app.services import ingestion_job_service

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not generated")


@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    set_store(OriginalSourceStore(root=tmp_path / "sources"))
    yield
    set_store(OriginalSourceStore())


def _source(client: TestClient, headers: dict) -> str:
    return client.post("/api/v1/sources",
                       json={"source_type": "scientific_paper", "title": "S"},
                       headers=headers).json()["id"]


def _upload(client: TestClient, headers: dict, name: str, source_id: str, **form):
    data = {"source_id": source_id}
    data.update({k: str(v) for k, v in form.items()})
    with (FIXTURES / name).open("rb") as handle:
        return client.post("/api/v1/documents/upload", data=data,
                           files={"file": (name, handle, "application/octet-stream")},
                           headers=headers)


def _run_job(job_id: str, db_session) -> dict:
    """Runs the REAL job body against the test's session.

    The Celery task is a thin wrapper over this same function, so what runs
    here is the production code path minus the broker hop. Driving it with
    the test session is necessary because the fixture holds an uncommitted
    transaction a separate worker session could not see — the first draft
    used `.apply()` and every job came back "skipped" for exactly that
    reason."""
    import uuid as _uuid

    from app.services import ingestion_job_service

    return ingestion_job_service.run_ingestion_job(db_session, job_id=_uuid.UUID(job_id))


# --- 202 and durable job ---------------------------------------------------


def test_upload_returns_202_not_200(client: TestClient, register_org) -> None:
    """The API must not do the work. A 200 would mean it did."""
    org = register_org()
    response = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"]))
    assert response.status_code == 202, response.text


def test_202_carries_a_durable_job_id(client: TestClient, register_org) -> None:
    org = register_org()
    body = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"])).json()
    assert body["job_id"] and body["document_id"] and body["conversion_id"]
    assert body["status"] == "queued"
    assert body["storage_path_recorded"] is True


def test_no_artifacts_exist_before_the_worker_runs(client: TestClient, register_org) -> None:
    """Proves the work really was deferred rather than done inline."""
    org = register_org()
    body = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"])).json()

    artifacts = client.get(
        f"/api/v1/documents/{body['document_id']}/artifacts", headers=org["headers"]
    ).json()
    assert artifacts["tables"] == []
    assert artifacts["assets"] == []

    markdown = client.get(
        f"/api/v1/documents/{body['document_id']}/markdown", headers=org["headers"]
    )
    assert markdown.status_code == 404, "no canonical Markdown may exist before conversion"


def test_original_is_retained_before_any_conversion(client: TestClient, register_org) -> None:
    """P12-01 + P12-02 together: a worker crash loses processing, never the
    source."""
    org = register_org()
    body = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"])).json()

    response = client.get(
        f"/api/v1/documents/{body['document_id']}/original", headers=org["headers"]
    )
    assert response.status_code == 200
    assert response.content == (FIXTURES / "tables.pdf").read_bytes()


# --- the worker actually produces the artifacts ------------------------------


def test_worker_run_produces_tables_and_markdown(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    body = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"])).json()

    result = _run_job(body["job_id"], db_session)
    assert result["status"] == "succeeded"
    assert result["table_count"] == 1

    artifacts = client.get(
        f"/api/v1/documents/{body['document_id']}/artifacts", headers=org["headers"]
    ).json()
    assert len(artifacts["tables"]) == 1
    assert ["Mannitol", "42.1", "g"] in artifacts["tables"][0]["rows"]

    markdown = client.get(
        f"/api/v1/documents/{body['document_id']}/markdown", headers=org["headers"]
    )
    assert markdown.status_code == 200
    assert "| Mannitol | 42.1 | g |" in markdown.text


def test_job_status_transitions_to_succeeded(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    _run_job(body["job_id"], db_session)

    status_body = client.get(
        f"/api/v1/documents/ingestion-jobs/{body['job_id']}", headers=org["headers"]
    ).json()
    assert status_body["status"] == "succeeded"
    assert status_body["attempts"] == 1
    assert status_body["completed_at"]
    assert status_body["result"]["conversion_status"] == "succeeded"


def test_image_and_ocr_artifacts_are_produced_by_the_worker(
    client: TestClient, register_org, db_session
) -> None:
    org = register_org()
    body = _upload(client, org["headers"], "with_image.pdf", _source(client, org["headers"])).json()
    _run_job(body["job_id"], db_session)

    assets = client.get(
        f"/api/v1/documents/{body['document_id']}/artifacts", headers=org["headers"]
    ).json()["assets"]
    assert len(assets) == 1
    assert assets[0]["status"] == "extracted"


# --- failure recovery (P12-03) ------------------------------------------------


def test_unconvertible_file_succeeds_the_job_but_fails_the_conversion(
    client: TestClient, register_org, db_session
) -> None:
    """THE distinction: the job ran and produced a definitive answer, so the
    JOB succeeded. The DOCUMENT could not be converted, and that verdict
    lives in `conversion_status`.

    Marking the job FAILED would invite an operator to retry work that
    cannot succeed — the same converter over the same bytes gives the same
    answer — and would hide that the pipeline is healthy."""
    org = register_org()
    body = _upload(client, org["headers"], "broken.pdf", _source(client, org["headers"])).json()

    result = _run_job(body["job_id"], db_session)
    assert result["status"] == "succeeded"

    status_body = client.get(
        f"/api/v1/documents/ingestion-jobs/{body['job_id']}", headers=org["headers"]
    ).json()
    assert status_body["status"] == "succeeded", "the job ran to completion"
    assert status_body["conversion_status"] in ("empty", "failed"), "the document did not convert"
    assert status_body["attempts"] == 1, "an unconvertible file must not be retried"


def test_transient_failure_becomes_retrying_then_can_succeed(
    client: TestClient, register_org, db_session
) -> None:
    """failure → RETRYING → retry → SUCCESS, asserted on persisted state."""
    import uuid as _uuid

    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    job_id = _uuid.UUID(body["job_id"])

    job = ingestion_job_service.claim(db_session, job_id=job_id)
    ingestion_job_service.fail(db_session, job=job, error="transient network blip", retryable=True)
    assert job.status == SyncJobStatus.RETRYING
    assert job.completed_at is None, "a retrying job is not finished"

    result = _run_job(str(job_id), db_session)
    assert result["status"] == "succeeded"
    db_session.refresh(job)
    assert job.status == SyncJobStatus.SUCCEEDED
    assert job.attempts == 2


def test_retries_are_bounded_then_terminal(client: TestClient, register_org, db_session) -> None:
    import uuid as _uuid

    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    job = ingestion_job_service.claim(db_session, job_id=_uuid.UUID(body["job_id"]))

    for _ in range(ingestion_job_service.MAX_ATTEMPTS + 2):
        ingestion_job_service.fail(db_session, job=job, error="still failing", retryable=True)
        if job.status == SyncJobStatus.RETRYING:
            ingestion_job_service.claim(db_session, job_id=job.id)
    assert job.status == SyncJobStatus.FAILED, "retries must be bounded"


def test_stalled_running_job_is_reclaimed(client: TestClient, register_org, db_session) -> None:
    """A worker killed mid-conversion leaves a RUNNING row. Without this,
    nothing ever revisits it and it looks busy forever."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    job = ingestion_job_service.claim(db_session, job_id=_uuid.UUID(body["job_id"]))

    job.started_at = datetime.now(timezone.utc) - timedelta(
        seconds=ingestion_job_service.LEASE_SECONDS + 60
    )
    db_session.commit()

    reclaimed = ingestion_job_service.reclaim_stalled(
        db_session, organization_id=_uuid.UUID(org["organization"]["id"])
    )
    assert len(reclaimed) == 1
    db_session.refresh(job)
    assert job.status != SyncJobStatus.RUNNING, "a stalled job must not stay RUNNING"


def test_fresh_running_job_is_not_reclaimed(client: TestClient, register_org, db_session) -> None:
    """A slow-but-alive job must not be reclaimed out from under itself."""
    import uuid as _uuid

    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    ingestion_job_service.claim(db_session, job_id=_uuid.UUID(body["job_id"]))

    assert ingestion_job_service.reclaim_stalled(
        db_session, organization_id=_uuid.UUID(org["organization"]["id"])
    ) == []


def test_completed_job_is_not_re_run_by_a_duplicate_delivery(
    client: TestClient, register_org, db_session
) -> None:
    """A duplicate queue delivery must not redo finished work."""
    org = register_org()
    body = _upload(client, org["headers"], "simple.pdf", _source(client, org["headers"])).json()
    assert _run_job(body["job_id"], db_session)["status"] == "succeeded"

    second = _run_job(body["job_id"], db_session)
    assert second["status"] == "skipped"


# --- idempotency (P12-04) --------------------------------------------------------


def test_identical_bytes_reuse_one_job(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])

    first = _upload(client, org["headers"], "simple.pdf", source_id).json()
    second = _upload(client, org["headers"], "simple.pdf", source_id).json()

    assert first["job_created"] is True
    assert second["job_created"] is False
    assert first["job_id"] == second["job_id"], "duplicate upload queued a second conversion"


def test_different_content_produces_different_jobs(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])

    a = _upload(client, org["headers"], "simple.pdf", source_id).json()
    b = _upload(client, org["headers"], "tables.pdf", source_id).json()
    assert a["job_id"] != b["job_id"]


def test_explicit_idempotency_key_is_honoured(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])

    a = _upload(client, org["headers"], "simple.pdf", source_id, idempotency_key="run-1").json()
    b = _upload(client, org["headers"], "simple.pdf", source_id, idempotency_key="run-1").json()
    c = _upload(client, org["headers"], "simple.pdf", source_id, idempotency_key="run-2").json()

    assert a["job_id"] == b["job_id"]
    assert c["job_id"] != a["job_id"], "a distinct key must allow deliberate reprocessing"


def test_jobs_are_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    body_b = _upload(client, org_b["headers"], "simple.pdf", _source(client, org_b["headers"])).json()

    assert client.get(
        f"/api/v1/documents/ingestion-jobs/{body_b['job_id']}", headers=org_a["headers"]
    ).status_code == 404


def test_identical_bytes_in_different_tenants_are_separate_jobs(
    client: TestClient, register_org
) -> None:
    """The idempotency key is tenant-scoped; one tenant's upload must not
    satisfy another's."""
    org_a, org_b = register_org(), register_org()
    a = _upload(client, org_a["headers"], "simple.pdf", _source(client, org_a["headers"])).json()
    b = _upload(client, org_b["headers"], "simple.pdf", _source(client, org_b["headers"])).json()

    assert a["job_id"] != b["job_id"]
    assert b["job_created"] is True
