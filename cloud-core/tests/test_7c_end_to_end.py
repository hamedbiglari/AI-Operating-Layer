"""
End-to-end scenarios A-J for Step 7C (7C-4 stage events + 7C-5 job object and
merge): real upload, reprocess and URL ingestion paths, then one GET of
/documents/{id}/processing.

The job body runs against the test session, as in test_stage_events: only the
broker hop is left out.
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ingestion import pipeline, url_source
from app.ingestion.converter import ConversionResult, ConversionStatus
from app.ingestion.extractors import ExtractionLevel, ExtractionResult
from app.ingestion.storage import OriginalSourceStore, set_store
from app.models.document_chunk import DocumentChunk
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage
from app.services import ingestion_job_service, ingestion_service, stage_events

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not generated")

FLAG = "AIOL_EMIT_STAGE_EVENTS"
KEYS = ["upload", "security", "conversion", "structure", "ocr", "chunking", "evidence", "knowledge"]
ROWED = ("upload", "security", "conversion", "structure", "ocr")
NOT_RUN = "not run (conversion failed)"


@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    set_store(OriginalSourceStore(root=tmp_path / "sources"))
    yield
    set_store(OriginalSourceStore())


def _source(client: TestClient, headers: dict) -> str:
    return client.post("/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"}, headers=headers).json()["id"]


def _upload(client: TestClient, headers: dict, name: str, source_id: str | None = None) -> dict:
    with (FIXTURES / name).open("rb") as handle:
        response = client.post("/api/v1/documents/upload", data={"source_id": source_id or _source(client, headers)},
                               files={"file": (name, handle, "application/octet-stream")}, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def _run(db, job_id) -> dict:
    return ingestion_job_service.run_ingestion_job(db, job_id=uuid.UUID(str(job_id)))


def _get(client: TestClient, headers: dict, document_id) -> dict:
    response = client.get(f"/api/v1/documents/{document_id}/processing", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _stages(body: dict) -> dict:
    return {s["key"]: (s["state"], s["detail"]) for s in body["stages"]}


def _rows(db, job_id) -> dict:
    db.expire_all()
    rows = db.execute(select(SyncJobStage).where(SyncJobStage.sync_job_id == uuid.UUID(str(job_id)))).scalars()
    return {r.stage_key.value: (r.state.value, r.detail) for r in rows}


def _chunking(db, document_id) -> str:
    n = db.execute(select(func.count()).select_from(DocumentChunk)
                   .where(DocumentChunk.document_id == uuid.UUID(str(document_id)))).scalar_one()
    return "done" if n else "pending"


def _crash(*args, **kwargs):
    raise RuntimeError("converter crashed")


def _converted(status: ConversionStatus, error: str | None):
    def run(*args, **kwargs):
        return pipeline.PipelineResult(
            conversion=ConversionResult(status, None, "markitdown", "x", "h", 1, None, 0, 0.0, error),
            extraction=ExtractionResult(level_used=ExtractionLevel.NORMALIZE), canonical_markdown=None)
    return run


def test_a_fresh_upload_flag_off(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    headers = register_org()["headers"]
    up = _upload(client, headers, "simple.pdf")
    assert _run(db_session, up["job_id"])["status"] == "succeeded"

    body = _get(client, headers, up["document_id"])
    assert _rows(db_session, up["job_id"]) == {}
    assert (body["job"]["id"], body["job"]["status"], body["job"]["attempts"]) == (up["job_id"], "succeeded", 1)
    stages = _stages(body)
    assert list(stages) == KEYS
    assert [stages[k][0] for k in ("upload", "security", "conversion")] == ["done", "done", "done"]
    assert stages["evidence"] == stages["knowledge"] == ("not_tracked", None)


def test_b_fresh_upload_flag_on(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    up = _upload(client, headers, "tables.pdf")
    assert _run(db_session, up["job_id"])["status"] == "succeeded"

    rows = _rows(db_session, up["job_id"])
    assert set(rows) == set(ROWED)
    stages = _stages(_get(client, headers, up["document_id"]))
    assert {k: stages[k] for k in ROWED} == rows                     # rows win, upload/security included (D26)
    assert stages["chunking"][0] == _chunking(db_session, up["document_id"])
    assert stages["evidence"] == stages["knowledge"] == ("not_tracked", None)


def test_c_url_job_has_no_job_object(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    monkeypatch.setattr(url_source, "fetch_url", lambda url, **kw: url_source.FetchedResource(
        url=url, final_url=url, content=b"<html><body><h1>T</h1><p>Some text.</p></body></html>",
        content_type="text/html", status_code=200, resolved_ip="93.184.216.34"))
    response = client.post("/api/v1/documents/ingest-url", json={"source_id": _source(client, headers),
                                                                  "url": "https://example.com/a"}, headers=headers)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    outcome = _run(db_session, job_id)
    assert outcome["status"] == "succeeded", outcome
    assert db_session.get(SyncJob, uuid.UUID(job_id)).document_id is None   # D19

    body = _get(client, headers, outcome["document_id"])
    assert body["job"] is None
    assert [s["key"] for s in body["stages"]] == KEYS


def test_d_document_without_any_job(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    doc = client.post(f"/api/v1/documents?source_id={_source(client, headers)}", json={"title": "D", "content": "text"},
                      headers=headers).json()
    body = _get(client, headers, doc["id"])
    assert body["job"] is None
    assert [s["key"] for s in body["stages"]] == KEYS


def test_e_failed_reprocess(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    up = _upload(client, headers, "tables.pdf")
    assert _run(db_session, up["job_id"])["status"] == "succeeded"
    before = _get(client, headers, up["document_id"])

    r = client.post(f"/api/v1/documents/{up['document_id']}/reprocess", headers=headers)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    monkeypatch.setattr(ingestion_service, "process_document", _crash)
    for _ in range(ingestion_job_service.MAX_ATTEMPTS):
        _run(db_session, job_id)

    body = _get(client, headers, up["document_id"])
    assert (body["job"]["id"], body["job"]["status"], body["job"]["attempts"]) == (job_id, "failed", 3)
    stages = _stages(body)
    for key in ("conversion", "structure", "ocr"):
        assert stages[key][0] == "failed" and "converter crashed" in stages[key][1]
    assert set(_rows(db_session, job_id)) == {"conversion", "structure", "ocr"}   # no upload/security rows
    assert stages["upload"] == stages["security"] == ("done", None)               # derived
    assert stages["chunking"] == _stages(before)["chunking"]
    assert body["metrics"] == before["metrics"]                                   # the old conversion is still current


def test_f_successful_reprocess(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    up = _upload(client, headers, "tables.pdf")
    _run(db_session, up["job_id"])
    r = client.post(f"/api/v1/documents/{up['document_id']}/reprocess", headers=headers)
    job_id = r.json()["job_id"]
    assert _run(db_session, job_id)["status"] == "succeeded"

    body = _get(client, headers, up["document_id"])
    assert (body["job"]["id"], body["job"]["status"]) == (job_id, "succeeded")
    assert body["job"]["id"] != up["job_id"]
    stages = _stages(body)
    rows = _rows(db_session, job_id)
    assert {k: stages[k] for k in ("conversion", "structure", "ocr")} == rows
    assert stages["upload"] == stages["security"] == ("done", None)


def test_g_stuck_active_rows(client: TestClient, register_org, db_session, monkeypatch) -> None:
    """D18 debt: a worker that died mid-run leaves its rows active; 7C-5 reports them as they are."""
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    up = _upload(client, headers, "simple.pdf")
    job = ingestion_job_service.claim(db_session, job_id=uuid.UUID(up["job_id"]))
    stage_events.start_run(db_session, job_id=job.id, organization_id=job.organization_id)
    db_session.flush()

    body = _get(client, headers, up["document_id"])
    assert body["job"]["status"] == "running"
    assert [_stages(body)[k][0] for k in ("conversion", "structure", "ocr")] == ["active", "active", "active"]


def test_h_two_meanings_of_not_tracked(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    up = _upload(client, headers, "simple.pdf")
    monkeypatch.setattr(ingestion_service, "process_document", _converted(ConversionStatus.FAILED, "boom"))
    assert _run(db_session, up["job_id"])["status"] == "succeeded"

    stages = _stages(_get(client, headers, up["document_id"]))
    assert stages["conversion"] == ("failed", "boom")
    assert stages["structure"] == stages["ocr"] == ("not_tracked", NOT_RUN)
    assert stages["evidence"] == stages["knowledge"] == ("not_tracked", None)


def test_i_other_organizations_document_is_404(client: TestClient, register_org, db_session) -> None:
    mine, theirs = register_org()["headers"], register_org()["headers"]
    up = _upload(client, theirs, "simple.pdf")
    _run(db_session, up["job_id"])
    assert client.get(f"/api/v1/documents/{up['document_id']}/processing", headers=mine).status_code == 404


def test_j_reupload_reuses_the_job_and_one_get_is_enough(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    headers = register_org()["headers"]
    source_id = _source(client, headers)
    first = _upload(client, headers, "simple.pdf", source_id)
    _run(db_session, first["job_id"])
    second = _upload(client, headers, "simple.pdf", source_id)
    assert second["job_id"] == first["job_id"] and second["job_created"] is False

    pairs = db_session.execute(select(SyncJobStage.stage_key, func.count()).where(
        SyncJobStage.sync_job_id == uuid.UUID(first["job_id"])).group_by(SyncJobStage.stage_key)).all()
    assert len(pairs) == 5 and all(n == 1 for _, n in pairs)

    body = _get(client, headers, first["document_id"])                # Rule 17: one request
    assert [s["key"] for s in body["stages"]] == KEYS
    assert body["job"]["id"] == first["job_id"] and body["metrics"]["pages"] is not None
