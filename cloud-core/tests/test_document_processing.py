"""
Integration tests for GET /documents/{id}/processing (Step 7C-1). Conversions
and chunks have no API that sets their state directly, so they are written to
the database, as in test_sources_overview.py; evidence and claims go through
the API.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentConversionStatus, DocumentExtractionStatus

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
