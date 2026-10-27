"""
Stage events from ingestion (Step 7C-4): what the real upload -> job -> worker
chain writes to sync_job_stages, with AIOL_EMIT_STAGE_EVENTS off and on.

The job body runs against the test session, as in test_async_ingestion: only
the broker hop is left out.
"""

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ingestion import pipeline
from app.ingestion.converter import ConversionResult, ConversionStatus
from app.ingestion.extractors import ExtractionLevel, ExtractionResult
from app.ingestion.storage import OriginalSourceStore, set_store
from app.models.enums import SyncJobStageKey as Key, SyncJobStageState as State, SyncJobStatus
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage
from app.services import ingestion_job_service, ingestion_service

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not generated")

FLAG = "AIOL_EMIT_STAGE_EVENTS"


@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    set_store(OriginalSourceStore(root=tmp_path / "sources"))
    yield
    set_store(OriginalSourceStore())


def _upload(client: TestClient, headers: dict, name: str) -> uuid.UUID:
    source_id = client.post("/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"},
                            headers=headers).json()["id"]
    with (FIXTURES / name).open("rb") as handle:
        response = client.post("/api/v1/documents/upload", data={"source_id": source_id},
                               files={"file": (name, handle, "application/octet-stream")}, headers=headers)
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["job_id"])


def _stages(db, job_id: uuid.UUID) -> dict[Key, SyncJobStage]:
    db.expire_all()
    rows = db.execute(select(SyncJobStage).where(SyncJobStage.sync_job_id == job_id)).scalars().all()
    return {row.stage_key: row for row in rows}


def _crash(*args, **kwargs):
    raise RuntimeError("converter crashed")


def _converted(status: ConversionStatus, error: str | None):
    """A pipeline that returns normally with this conversion verdict, as pipeline.py does for a bad file."""
    def run(*args, **kwargs):
        return pipeline.PipelineResult(
            conversion=ConversionResult(status, None, "markitdown", "x", "h", 1, None, 0, 0.0, error),
            extraction=ExtractionResult(level_used=ExtractionLevel.NORMALIZE), canonical_markdown=None)
    return run


def test_flag_off_writes_no_stage_rows(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.delenv(FLAG, raising=False)
    job_id = _upload(client, register_org()["headers"], "tables.pdf")
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"
    assert _stages(db_session, job_id) == {}


def test_flag_on_upload_writes_five_done_stages(client: TestClient, register_org, db_session, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "tables.pdf")
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"

    stages = _stages(db_session, job_id)
    assert set(stages) == {Key.UPLOAD, Key.SECURITY, Key.CONVERSION, Key.STRUCTURE, Key.OCR}
    assert all(s.state == State.DONE for s in stages.values())
    created = db_session.get(SyncJob, job_id).created_at
    for key in (Key.UPLOAD, Key.SECURITY):
        assert stages[key].started_at == stages[key].completed_at == created
    run = [stages[k] for k in (Key.CONVERSION, Key.STRUCTURE, Key.OCR)]
    assert len({s.completed_at for s in run}) == 1, "one pipeline call, one completion time"
    assert all(s.started_at is not None and s.started_at <= s.completed_at for s in run)
    assert stages[Key.CONVERSION].detail is None
    assert re.fullmatch(r"1 table|(0|[2-9]|\d{2,}) tables", stages[Key.STRUCTURE].detail)
    assert re.fullmatch(r"1 OCR block|(0|[2-9]|\d{2,}) OCR blocks", stages[Key.OCR].detail)


def test_flag_on_crashed_run_marks_its_stages_failed(
    client: TestClient, register_org, db_session, monkeypatch
) -> None:
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "simple.pdf")
    monkeypatch.setattr(ingestion_service, "process_document", _crash)
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "error"

    stages = _stages(db_session, job_id)
    assert stages[Key.UPLOAD].state == stages[Key.SECURITY].state == State.DONE
    for key in (Key.CONVERSION, Key.STRUCTURE, Key.OCR):
        assert stages[key].state == State.FAILED
        assert "converter crashed" in stages[key].detail and stages[key].completed_at is not None


@pytest.mark.parametrize("status", [ConversionStatus.FAILED, ConversionStatus.UNSUPPORTED])
def test_flag_on_failed_conversion_marks_later_stages_not_run(
    client: TestClient, register_org, db_session, monkeypatch, status
) -> None:
    """No exception and the job succeeds, but the file did not convert: the
    stage rows must say so, not report three finished stages."""
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "simple.pdf")
    monkeypatch.setattr(ingestion_service, "process_document", _converted(status, "boom"))
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"

    stages = _stages(db_session, job_id)
    assert (stages[Key.CONVERSION].state, stages[Key.CONVERSION].detail) == (State.FAILED, "boom")
    for key in (Key.STRUCTURE, Key.OCR):
        assert (stages[key].state, stages[key].detail) == (State.NOT_TRACKED, "not run (conversion failed)")
        assert stages[key].started_at is None and stages[key].completed_at is None


def test_flag_on_empty_conversion_still_finishes_structure_and_ocr(
    client: TestClient, register_org, db_session, monkeypatch
) -> None:
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "simple.pdf")
    monkeypatch.setattr(ingestion_service, "process_document", _converted(ConversionStatus.EMPTY, None))
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"

    stages = _stages(db_session, job_id)
    assert (stages[Key.CONVERSION].state, stages[Key.CONVERSION].detail) == (State.FAILED, "no usable text")
    assert (stages[Key.STRUCTURE].state, stages[Key.STRUCTURE].detail) == (State.DONE, "0 tables")
    assert (stages[Key.OCR].state, stages[Key.OCR].detail) == (State.DONE, "0 OCR blocks")


def test_retry_of_the_same_job_replaces_the_failed_attempts_rows(
    client: TestClient, register_org, db_session, monkeypatch
) -> None:
    """Retries reuse the job id; without the reset in claim() the second run's
    inserts would hit the (sync_job_id, stage_key) unique constraint."""
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "simple.pdf")
    with monkeypatch.context() as patch:
        patch.setattr(ingestion_service, "process_document", _crash)
        ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)
    assert db_session.get(SyncJob, job_id).status == SyncJobStatus.RETRYING

    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"
    job = db_session.get(SyncJob, job_id)
    assert job.attempts == 2
    stages = _stages(db_session, job_id)
    assert len(stages) == 5 and all(s.state == State.DONE for s in stages.values())
    assert all(stages[k].started_at >= job.started_at for k in (Key.CONVERSION, Key.STRUCTURE, Key.OCR))


def test_flag_turned_off_after_upload_writes_nothing_more(
    client: TestClient, register_org, db_session, monkeypatch
) -> None:
    monkeypatch.setenv(FLAG, "true")
    job_id = _upload(client, register_org()["headers"], "tables.pdf")
    monkeypatch.setenv(FLAG, "false")
    assert ingestion_job_service.run_ingestion_job(db_session, job_id=job_id)["status"] == "succeeded"
    assert set(_stages(db_session, job_id)) == {Key.UPLOAD, Key.SECURITY}
