"""
Integration tests for GET /sources/{id}/documents: each row carries its
current conversion, so the Source detail list needs no call per document.
Conversions have no API that sets their state directly, so they are written
to the database, as in test_sources_overview.py.
"""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.models.document_artifact import DocumentConversion
from app.models.enums import DocumentConversionStatus


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _source(client: TestClient, headers: dict, title: str = "S") -> dict:
    return _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": title})


def _doc(client: TestClient, headers: dict, source: dict, title: str = "D") -> dict:
    return _post(client, headers, f"/api/v1/documents?source_id={source['id']}", {"title": title, "content": "text"})


def _conversion(db, doc: dict, status: str, *, current: bool = True, needs_review: bool = False) -> DocumentConversion:
    conv = DocumentConversion(
        organization_id=uuid.UUID(doc["organization_id"]), document_id=uuid.UUID(doc["id"]),
        original_filename="f.pdf", source_hash="0" * 64, source_size_bytes=1, source_mime_type="application/pdf",
        converter_name="test", converter_version="1", conversion_status=DocumentConversionStatus(status),
        is_current=current, superseded_at=None if current else datetime.now(timezone.utc),
        needs_review=needs_review, review_reasons=["low text confidence"] if needs_review else [],
    )
    db.add(conv)
    db.flush()
    return conv


def _items(client: TestClient, headers: dict, source: dict, query: str = "") -> dict:
    response = client.get(f"/api/v1/sources/{source['id']}/documents{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_current_conversion_is_on_the_row(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers)
    doc = _doc(client, headers, source)
    conv = _conversion(db_session, doc, "succeeded", needs_review=True)

    [item] = _items(client, headers, source)["items"]
    assert item["current_conversion"] == {"id": str(conv.id), "status": "succeeded", "needs_review": True}


def test_document_without_conversions_has_none(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers)
    _doc(client, headers, source)

    [item] = _items(client, headers, source)["items"]
    assert (item["current_conversion"], item["extraction_status"]) == (None, "pending")


def test_only_the_current_conversion_is_returned(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers)
    doc = _doc(client, headers, source)
    _conversion(db_session, doc, "failed", current=False)
    current = _conversion(db_session, doc, "empty")

    body = _items(client, headers, source)
    assert body["total"] == 1                                     # the join added no row
    assert body["items"][0]["current_conversion"] == {"id": str(current.id), "status": "empty", "needs_review": False}


def test_other_organizations_documents_never_appear(client: TestClient, register_org, db_session) -> None:
    # Regression guard: tenant scoping existed before current_conversion was added.
    mine, theirs = register_org()["headers"], register_org()["headers"]
    source = _source(client, mine)
    _doc(client, mine, source, "Mine")
    their_source = _source(client, theirs)
    _conversion(db_session, _doc(client, theirs, their_source, "Theirs"), "succeeded")

    assert [d["title"] for d in _items(client, mine, source)["items"]] == ["Mine"]
    assert client.get(f"/api/v1/sources/{their_source['id']}/documents", headers=mine).status_code == 404


def test_rows_carry_no_text(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers)
    _doc(client, headers, source)

    [item] = _items(client, headers, source)["items"]
    assert "content" not in item


def test_paging(client: TestClient, register_org, db_session) -> None:
    # Regression guard: limit/offset/total behaved this way before current_conversion was added.
    headers = register_org()["headers"]
    source = _source(client, headers)
    for title in ("A", "B", "C"):
        _conversion(db_session, _doc(client, headers, source, title), "succeeded")

    first, rest = _items(client, headers, source, "?limit=2&offset=0"), _items(client, headers, source, "?limit=2&offset=2")
    assert [(b["total"], b["limit"], b["offset"], len(b["items"])) for b in (first, rest)] == [(3, 2, 0, 2), (3, 2, 2, 1)]
    assert len({d["id"] for d in first["items"] + rest["items"]}) == 3
