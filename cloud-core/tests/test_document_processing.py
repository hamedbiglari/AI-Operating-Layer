"""
Integration tests for GET /documents/{id}/processing (Steps 7C-1, 7C-5).
Conversions, chunks, jobs and stage rows have no API that sets their state
directly, so they are written to the database, as in test_sources_overview.py;
evidence and claims go through the API.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentConversionStatus, DocumentExtractionStatus, SyncJobStageKey as Key, SyncJobStageState as State,
    SyncJobStatus, SyncJobType,
)
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage

KEYS = ["upload", "security", "conversion", "structure", "ocr", "chunking", "evidence", "knowledge"]
STATES = {"done", "active", "pending", "failed", "not_tracked"}


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _document(client: TestClient, headers: dict) -> tuple[dict, dict]:
    source = _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": "S"})
    return source, _post(client, headers, f"/api/v1/documents?source_id={source['id']}", {"title": "D", "content": "text"})


def _conversion(db, doc: dict, state: str, tables: int = 0, ocr_blocks: int = 0) -> None:
    db.add(DocumentConversion(
        organization_id=uuid.UUID(doc["organization_id"]), document_id=uuid.UUID(doc["id"]),
        original_filename="f.pdf", source_hash="0" * 64, source_size_bytes=1, source_mime_type="application/pdf",
        converter_name="test", converter_version="1", conversion_status=DocumentConversionStatus.SUCCEEDED,
        processing_state=state, page_count=9, table_count=tables, image_count=2, ocr_block_count=ocr_blocks,
        review_reasons=["test"] if state == "needs_review" else [],
    ))
    db.flush()


def _chunks(db, doc: dict, n: int) -> None:
    for i in range(n):
        db.add(DocumentChunk(organization_id=uuid.UUID(doc["organization_id"]), document_id=uuid.UUID(doc["id"]),
                             chunk_index=i, content="c%d" % i))
    db.flush()


def _claim(client: TestClient, headers: dict, name: str) -> dict:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": name, "object_type": "plant"})
    subject = _post(client, headers, "/api/v1/entities",
                    {"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": name})
    return _post(client, headers, "/api/v1/claims", {
        "knowledge_object_id": ko["id"], "subject_entity_id": subject["id"], "predicate": "contains", "object_value": "x"})


def _processing(client: TestClient, headers: dict, doc: dict) -> dict:
    response = client.get(f"/api/v1/documents/{doc['id']}/processing", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _states(body: dict) -> dict:
    return {s["key"]: s["state"] for s in body["stages"]}


def test_processed_document_with_everything(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=3, ocr_blocks=5)
    _chunks(db_session, doc, 12)
    evidence = [_post(client, headers, "/api/v1/evidence", {"source_id": source["id"], "document_id": doc["id"], "summary": "E%d" % i})
                for i in range(4)]
    for claim, ev in zip((_claim(client, headers, "A"), _claim(client, headers, "B")), evidence):
        _post(client, headers, "/api/v1/claim-evidence", {"claim_id": claim["id"], "evidence_id": ev["id"]})

    body = _processing(client, headers, doc)
    assert _states(body) == {"upload": "done", "security": "done", "conversion": "done", "structure": "done", "ocr": "done",
                             "chunking": "done", "evidence": "not_tracked", "knowledge": "not_tracked"}
    details = {s["key"]: s["detail"] for s in body["stages"]}
    assert (details["structure"], details["ocr"]) == ("3 tables", "5 OCR blocks")
    assert body["metrics"] == {"pages": 9, "tables": 3, "images": 2, "ocr_blocks": 5, "chunks": 12, "claims": 2, "evidence": 4}


def test_conversion_still_processing(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processing")

    states = _states(_processing(client, headers, doc))
    assert [states[k] for k in ("conversion", "structure", "ocr", "chunking")] == ["active", "active", "active", "pending"]


def test_failed_conversion(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "failed")

    states = _states(_processing(client, headers, doc))
    assert [states[k] for k in ("upload", "security", "conversion", "structure", "ocr")] == ["done", "done", "failed", "failed", "failed"]


def test_no_conversion(client: TestClient, register_org, db_session) -> None:
    # Rule B: without a conversion row, upload is failed only when extraction failed.
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    body = _processing(client, headers, doc)
    assert (_states(body)["upload"], body["metrics"]["tables"]) == ("pending", None)

    db_session.execute(update(Document).where(Document.id == uuid.UUID(doc["id"]))
                       .values(extraction_status=DocumentExtractionStatus.FAILED))
    db_session.flush()
    assert [_states(_processing(client, headers, doc))[k] for k in ("upload", "security")] == ["failed", "failed"]


def test_zero_tables_is_a_finished_stage(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=0)

    structure = next(s for s in _processing(client, headers, doc)["stages"] if s["key"] == "structure")
    assert (structure["state"], structure["detail"]) == ("done", "0 tables")


def test_other_organizations_document_is_404(client: TestClient, register_org) -> None:
    mine, theirs = register_org()["headers"], register_org()["headers"]
    _, own = _document(client, mine)
    _, doc = _document(client, theirs)
    # The caller's own document answers, so the 404 below is isolation, not a missing route.
    assert client.get(f"/api/v1/documents/{own['id']}/processing", headers=mine).status_code == 200
    assert client.get(f"/api/v1/documents/{doc['id']}/processing", headers=mine).status_code == 404


def test_only_documented_keys_and_states(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    for state in ("queued", "processing", "processed", "partially_processed", "needs_review", "failed", "retrying", "completed"):
        _, doc = _document(client, headers)
        _conversion(db_session, doc, state)
        body = _processing(client, headers, doc)
        assert [s["key"] for s in body["stages"]] == KEYS
        assert {s["state"] for s in body["stages"]} <= STATES, (state, body["stages"])


# --- Step 7C-5: the latest job and its stage rows ---------------------------

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _job(db, doc: dict | None, status: SyncJobStatus, *, org: str | None = None, minutes: int = 0,
         attempts: int = 1, stages: dict | None = None) -> SyncJob:
    """A document-ingestion job created T0 + `minutes`; `doc=None` is a URL job (no document_id, D19)."""
    org_id = uuid.UUID(org or doc["organization_id"])
    job = SyncJob(organization_id=org_id, document_id=uuid.UUID(doc["id"]) if doc else None,
                  job_type=SyncJobType.DOCUMENT_INGESTION, status=status, attempts=attempts,
                  payload={"document_id": doc["id"]} if doc else {"kind": "url"},
                  created_at=T0 + timedelta(minutes=minutes), started_at=T0 + timedelta(minutes=minutes))
    db.add(job)
    db.flush()
    for key, (state, detail) in (stages or {}).items():
        db.add(SyncJobStage(organization_id=org_id, sync_job_id=job.id, stage_key=key, state=state, detail=detail))
    db.flush()
    return job


DONE5 = {Key.UPLOAD: (State.DONE, None), Key.SECURITY: (State.DONE, None), Key.CONVERSION: (State.DONE, None),
         Key.STRUCTURE: (State.DONE, "1 table"), Key.OCR: (State.DONE, "1 OCR block")}
NOT_RUN = "not run (conversion failed)"


def _details(body: dict) -> dict:
    return {s["key"]: s["detail"] for s in body["stages"]}


def test_stage_rows_win_over_derived_stages(client: TestClient, register_org, db_session) -> None:
    """T-A. The conversion still says processing (derived: active); the job's rows say done."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processing")
    job = _job(db_session, doc, SyncJobStatus.SUCCEEDED, stages=DONE5)

    body = _processing(client, headers, doc)
    assert _states(body) == {"upload": "done", "security": "done", "conversion": "done", "structure": "done", "ocr": "done",
                             "chunking": "pending", "evidence": "not_tracked", "knowledge": "not_tracked"}
    assert (_details(body)["structure"], _details(body)["ocr"]) == ("1 table", "1 OCR block")
    assert (body["job"]["id"], body["job"]["status"], body["job"]["attempts"]) == (str(job.id), "succeeded", 1)


def test_job_without_stage_rows_keeps_derived_stages(client: TestClient, register_org, db_session) -> None:
    """T-B. Flag off: a job but no rows, so every stage is derived as before 7C-5."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=3, ocr_blocks=5)
    _job(db_session, doc, SyncJobStatus.SUCCEEDED)

    body = _processing(client, headers, doc)
    assert {_states(body)[k] for k in ("upload", "security", "conversion", "structure", "ocr")} == {"done"}
    assert (_details(body)["structure"], _details(body)["ocr"]) == ("3 tables", "5 OCR blocks")
    assert body["job"]["status"] == "succeeded"


def test_url_job_without_document_id_gives_no_job(client: TestClient, register_org, db_session) -> None:
    """T-C. URL jobs never get document_id (D19), so the document shows no job."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed")
    _job(db_session, None, SyncJobStatus.SUCCEEDED, org=doc["organization_id"], stages=DONE5)

    body = _processing(client, headers, doc)
    assert body["job"] is None
    assert _details(body)["structure"] == "0 tables"   # derived, not the URL job's rows


def test_document_without_any_job(client: TestClient, register_org, db_session) -> None:
    """T-D."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed")
    body = _processing(client, headers, doc)
    assert body["job"] is None
    assert _states(body)["conversion"] == "done"


def test_failed_reprocess_shows_the_latest_attempt(client: TestClient, register_org, db_session) -> None:
    """T-E. The reprocess failed, so the old conversion stays current: run stages
    come from the failed job, upload/security and chunking are derived, metrics
    are the old conversion's."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=3)
    _chunks(db_session, doc, 2)
    _job(db_session, doc, SyncJobStatus.SUCCEEDED, stages=DONE5)
    failed = _job(db_session, doc, SyncJobStatus.FAILED, minutes=5, attempts=3, stages={
        Key.CONVERSION: (State.FAILED, "boom"), Key.STRUCTURE: (State.NOT_TRACKED, NOT_RUN),
        Key.OCR: (State.NOT_TRACKED, NOT_RUN)})

    body = _processing(client, headers, doc)
    assert (body["job"]["id"], body["job"]["status"], body["job"]["attempts"]) == (str(failed.id), "failed", 3)
    assert _states(body) == {"upload": "done", "security": "done", "conversion": "failed", "structure": "not_tracked",
                             "ocr": "not_tracked", "chunking": "done", "evidence": "not_tracked", "knowledge": "not_tracked"}
    assert (_details(body)["conversion"], _details(body)["structure"], _details(body)["ocr"]) == ("boom", NOT_RUN, NOT_RUN)
    assert (body["metrics"]["tables"], body["metrics"]["chunks"]) == (3, 2)


def test_successful_reprocess_shows_the_new_job(client: TestClient, register_org, db_session) -> None:
    """T-F. The newer job wins over an older failed one."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=1, ocr_blocks=1)
    _job(db_session, doc, SyncJobStatus.FAILED, stages={Key.CONVERSION: (State.FAILED, "old")})
    new = _job(db_session, doc, SyncJobStatus.SUCCEEDED, minutes=5, stages={
        k: v for k, v in DONE5.items() if k not in (Key.UPLOAD, Key.SECURITY)})   # reprocess: no upload/security rows

    body = _processing(client, headers, doc)
    assert (body["job"]["id"], body["job"]["status"]) == (str(new.id), "succeeded")
    assert {_states(body)[k] for k in ("upload", "security", "conversion", "structure", "ocr")} == {"done"}
    assert _details(body)["conversion"] is None


def test_one_call_returns_stages_metrics_and_job(client: TestClient, register_org, db_session) -> None:
    """T-G. Rule 17: one HTTP request carries the whole view."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed")
    _job(db_session, doc, SyncJobStatus.SUCCEEDED, stages=DONE5)

    body = _processing(client, headers, doc)
    assert [s["key"] for s in body["stages"]] == KEYS
    assert set(body["metrics"]) == {"pages", "tables", "images", "ocr_blocks", "chunks", "claims", "evidence"}
    assert set(body["job"]) == {"id", "status", "attempts", "created_at", "started_at", "completed_at"}


def test_other_organizations_job_is_not_shown(client: TestClient, register_org, db_session) -> None:
    """T-H. The other org's document is 404, and its job never reaches the caller."""
    mine, theirs = register_org()["headers"], register_org()["headers"]
    _, own = _document(client, mine)
    _, doc = _document(client, theirs)
    _job(db_session, doc, SyncJobStatus.SUCCEEDED, stages=DONE5)
    assert client.get(f"/api/v1/documents/{doc['id']}/processing", headers=mine).status_code == 404
    assert _processing(client, mine, own)["job"] is None


def test_stuck_active_rows_are_returned_as_they_are(client: TestClient, register_org, db_session) -> None:
    """T-J. D18/D25: a dead worker leaves rows active; 7C-5 reports them, the sweeper debt fixes them."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed")
    _job(db_session, doc, SyncJobStatus.RUNNING, stages={
        Key.CONVERSION: (State.ACTIVE, None), Key.STRUCTURE: (State.ACTIVE, None), Key.OCR: (State.ACTIVE, None)})

    body = _processing(client, headers, doc)
    assert [_states(body)[k] for k in ("conversion", "structure", "ocr")] == ["active", "active", "active"]
    assert body["job"]["status"] == "running"


def test_not_tracked_row_is_a_valid_response_state(client: TestClient, register_org, db_session) -> None:
    """T-K. D24: a NOT_TRACKED row maps onto the response's StageState."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed")
    _job(db_session, doc, SyncJobStatus.SUCCEEDED, stages={Key.OCR: (State.NOT_TRACKED, NOT_RUN)})

    ocr = next(s for s in _processing(client, headers, doc)["stages"] if s["key"] == "ocr")
    assert (ocr["state"], ocr["detail"]) == ("not_tracked", NOT_RUN)


def test_derived_counts_are_pluralized(client: TestClient, register_org, db_session) -> None:
    """D22: the derived details follow R3's wording."""
    headers = register_org()["headers"]
    _, doc = _document(client, headers)
    _conversion(db_session, doc, "processed", tables=1, ocr_blocks=1)
    details = _details(_processing(client, headers, doc))
    assert (details["structure"], details["ocr"]) == ("1 table", "1 OCR block")
