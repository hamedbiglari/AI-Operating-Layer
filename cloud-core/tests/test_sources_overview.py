"""
Integration tests for GET /sources/overview. Sources, evidence and claims are
created through the API; document extraction states, conversions and
content_access have no API that sets them directly, so they are written to
the database, the same way test_dashboard_summary.py seeds conversions.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.enums import DocumentConversionStatus, DocumentExtractionStatus
from app.models.source import Source

OVERVIEW = "/api/v1/sources/overview"
NO_STATUSES = {"failed": 0, "processing": 0, "completed": 0, "abstract_only": 0, "reference_only": 0}


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _source(client: TestClient, headers: dict, title: str, source_type: str = "website", **fields) -> dict:
    return _post(client, headers, "/api/v1/sources", {"source_type": source_type, "title": title, **fields})


def _doc(client: TestClient, headers: dict, db, source: dict, status: str = "extracted",
         conversion: str | None = None) -> dict:
    doc = _post(client, headers, f"/api/v1/documents?source_id={source['id']}", {"title": "D", "content": "text"})
    db.execute(update(Document).where(Document.id == uuid.UUID(doc["id"]))
               .values(extraction_status=DocumentExtractionStatus(status)))
    if conversion:
        db.add(DocumentConversion(
            organization_id=uuid.UUID(doc["organization_id"]), document_id=uuid.UUID(doc["id"]),
            original_filename="f.pdf", source_hash="0" * 64, source_size_bytes=1, source_mime_type="application/pdf",
            converter_name="test", converter_version="1", conversion_status=DocumentConversionStatus(conversion),
        ))
    db.flush()
    return doc


def _content_access(db, source: dict, value: str) -> None:
    db.execute(update(Source).where(Source.id == uuid.UUID(source["id"])).values(content_access=value))
    db.flush()


def _claim(client: TestClient, headers: dict, name: str) -> dict:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": name, "object_type": "plant"})
    subject = _post(client, headers, "/api/v1/entities",
                    {"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": name})
    return _post(client, headers, "/api/v1/claims", {
        "knowledge_object_id": ko["id"], "subject_entity_id": subject["id"], "predicate": "contains", "object_value": "x"})


def _evidence(client: TestClient, headers: dict, source: dict, *claims: dict) -> dict:
    evidence = _post(client, headers, "/api/v1/evidence", {"source_id": source["id"], "summary": "E"})
    for claim in claims:
        _post(client, headers, "/api/v1/claim-evidence", {"claim_id": claim["id"], "evidence_id": evidence["id"]})
    return evidence


def _overview(client: TestClient, headers: dict, query: str = "") -> dict:
    response = client.get(OVERVIEW + query, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _titles(body: dict) -> list[str]:
    return [item["title"] for item in body["items"]]


def test_overview_requires_authentication(client: TestClient) -> None:
    assert client.get(OVERVIEW).status_code == 401


# Each case: (documents as (extraction_status, current conversion_status or None), content_access, expected).
@pytest.mark.parametrize(("docs", "content_access", "expected"), [
    pytest.param([("failed", None)], "unknown", "failed", id="a-doc-failed"),
    pytest.param([("failed", "empty")], "unknown", "failed", id="a-empty-conversion-no-text"),
    pytest.param([("pending", None)], "unknown", "processing", id="b-doc-pending"),
    pytest.param([("extracting", None)], "unknown", "processing", id="b-doc-extracting"),
    pytest.param([("extracted", "pending")], "unknown", "processing", id="b-conversion-pending"),
    pytest.param([("extracted", "succeeded")], "unknown", "completed", id="c-converted"),
    pytest.param([("extracted", "empty")], "unknown", "completed", id="c-empty-conversion-ocr-rescued"),
    pytest.param([("extracted", None)], "unknown", "completed", id="c-text-doc-no-conversion-row"),
    pytest.param([], "abstract_only", "abstract_only", id="d-abstract-only"),
    pytest.param([], "unknown", "reference_only", id="e-reference-only"),
    pytest.param([], "metadata_only", "reference_only", id="e-metadata-only"),
])
def test_derived_status_rules(client: TestClient, register_org, db_session, docs, content_access, expected) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers, "S", doi="10.1000/x")
    for status, conversion in docs:
        _doc(client, headers, db_session, source, status, conversion)
    _content_access(db_session, source, content_access)

    item = _overview(client, headers)["items"][0]
    assert item["derived_status"] == expected
    assert item["counts"]["documents"] == len(docs)


def test_failed_document_outranks_completed_document(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers, "Mixed")
    _doc(client, headers, db_session, source, "extracted", "succeeded")
    _doc(client, headers, db_session, source, "failed")
    assert _overview(client, headers)["items"][0]["derived_status"] == "failed"


def test_processing_document_outranks_completed_document(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers, "Mixed")
    _doc(client, headers, db_session, source, "extracted")
    _doc(client, headers, db_session, source, "pending")
    assert _overview(client, headers)["items"][0]["derived_status"] == "processing"


def test_counts_follow_claim_links_without_double_counting(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    source = _source(client, headers, "Counted")
    _doc(client, headers, db_session, source)
    taranjabin, saffron = _claim(client, headers, "Taranjabin"), _claim(client, headers, "Saffron")
    _evidence(client, headers, source, taranjabin)
    _evidence(client, headers, source, taranjabin, saffron)   # the same claim again, plus a second object
    _evidence(client, headers, source)                        # evidence with no claim yet
    other = _source(client, headers, "Other")
    _evidence(client, headers, other, saffron)

    items = {i["title"]: i for i in _overview(client, headers)["items"]}
    assert items["Counted"]["counts"] == {"documents": 1, "knowledge_objects": 2, "claims": 2, "evidence": 3}
    assert items["Other"]["counts"] == {"documents": 0, "knowledge_objects": 1, "claims": 1, "evidence": 1}


def test_last_activity_is_the_newer_of_source_and_documents(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    quiet, reprocessed = _source(client, headers, "Quiet"), _source(client, headers, "Reprocessed")
    doc = _doc(client, headers, db_session, reprocessed)
    later = datetime.now(timezone.utc) + timedelta(days=3)
    db_session.execute(update(Document).where(Document.id == uuid.UUID(doc["id"])).values(updated_at=later))
    db_session.flush()

    items = {i["title"]: i for i in _overview(client, headers)["items"]}
    assert datetime.fromisoformat(items["Reprocessed"]["last_activity_at"]) == later
    assert items["Quiet"]["last_activity_at"] == items["Quiet"]["updated_at"]
    # mime_type and file_size come from the single document.
    assert (items["Reprocessed"]["mime_type"], items["Reprocessed"]["file_size"]) == ("text/plain", 4)
    assert (items["Quiet"]["mime_type"], items["Quiet"]["file_size"]) == (None, None)


def test_search_matches_title_doi_pmid_and_url(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _source(client, headers, "Mannitol in Alhagi")
    _source(client, headers, "By DOI", doi="10.1016/j.jep.2024.118233")
    _source(client, headers, "By PMID", pmid="39214477")
    _source(client, headers, "By URL", url="https://toranjebin.ir/products/grade-1")
    for query, title in (("mannitol", "Mannitol in Alhagi"), ("j.jep.2024", "By DOI"),
                         ("3921447", "By PMID"), ("TORANJEBIN.IR", "By URL")):
        assert _titles(_overview(client, headers, f"?search={query}")) == [title]


def test_source_type_filter(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _source(client, headers, "Paper", source_type="scientific_paper")
    _source(client, headers, "Site", source_type="website")
    body = _overview(client, headers, "?source_type=scientific_paper")
    assert (_titles(body), body["total"]) == (["Paper"], 1)


def test_status_filter(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _doc(client, headers, db_session, _source(client, headers, "Broken"), "failed")
    _doc(client, headers, db_session, _source(client, headers, "Done"))
    _source(client, headers, "Citation")
    body = _overview(client, headers, "?status=failed")
    assert (_titles(body), body["total"]) == (["Broken"], 1)


def test_sorts(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    garlic, saffron, thyme = (_source(client, headers, t) for t in ("Garlic", "Saffron", "Thyme"))
    a, b = _claim(client, headers, "A"), _claim(client, headers, "B")
    _evidence(client, headers, garlic, a, b)     # 2 claims, 1 evidence
    _evidence(client, headers, saffron)
    _evidence(client, headers, saffron)          # 0 claims, 2 evidence
    assert _titles(_overview(client, headers)) == ["Thyme", "Saffron", "Garlic"]
    assert _titles(_overview(client, headers, "?sort=name")) == ["Garlic", "Saffron", "Thyme"]
    assert _titles(_overview(client, headers, "?sort=claims")) == ["Garlic", "Thyme", "Saffron"]
    assert _titles(_overview(client, headers, "?sort=evidence")) == ["Saffron", "Garlic", "Thyme"]


def test_paging_leaves_total_and_status_counts_whole(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    for title in ("A", "B", "C"):
        _source(client, headers, title)
    body = _overview(client, headers, "?sort=name&limit=2&offset=2")
    assert (_titles(body), body["total"], body["limit"], body["offset"]) == (["C"], 3, 2, 2)
    assert body["counts_by_status"] == {**NO_STATUSES, "reference_only": 3}


def test_status_counts_ignore_status_filter_but_follow_search(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _doc(client, headers, db_session, _source(client, headers, "Saffron report"), "failed")
    _doc(client, headers, db_session, _source(client, headers, "Saffron paper"))
    _doc(client, headers, db_session, _source(client, headers, "Garlic paper"), "failed")
    body = _overview(client, headers, "?search=saffron&status=failed")
    assert (_titles(body), body["total"]) == (["Saffron report"], 1)
    assert body["counts_by_status"] == {**NO_STATUSES, "failed": 1, "completed": 1}


def test_status_counts_follow_source_type_filter(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    for source_type, failed, completed in (("url", 2, 3), ("pdf", 1, 4)):
        for i in range(failed):
            _doc(client, headers, db_session, _source(client, headers, f"{source_type} failed {i}", source_type), "failed")
        for i in range(completed):
            _doc(client, headers, db_session, _source(client, headers, f"{source_type} done {i}", source_type))
    body = _overview(client, headers, "?source_type=url&status=failed")
    assert sorted(_titles(body)) == ["url failed 0", "url failed 1"]
    assert body["total"] == 2
    assert body["counts_by_status"] == {**NO_STATUSES, "failed": 2, "completed": 3}


def test_other_organizations_sources_never_appear(client: TestClient, register_org, db_session) -> None:
    mine, theirs = register_org()["headers"], register_org()["headers"]
    _doc(client, mine, db_session, _source(client, mine, "Mine"))
    their_source = _source(client, theirs, "Theirs")
    _doc(client, theirs, db_session, their_source, "failed")
    _evidence(client, theirs, their_source, _claim(client, theirs, "X"))

    body = _overview(client, mine)
    assert (_titles(body), body["total"]) == (["Mine"], 1)
    assert body["items"][0]["counts"] == {"documents": 1, "knowledge_objects": 0, "claims": 0, "evidence": 0}
    assert body["counts_by_status"] == {**NO_STATUSES, "completed": 1}


def test_id_returns_that_source_row_only(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    _source(client, headers, "Other")
    wanted = _source(client, headers, "Wanted")
    _doc(client, headers, db_session, wanted, "failed")
    _evidence(client, headers, wanted, _claim(client, headers, "X"))
    list_row = next(item for item in _overview(client, headers)["items"] if item["id"] == wanted["id"])

    # The list's filters and paging do not reach the detail header's row.
    for query in (f"?id={wanted['id']}", f"?id={wanted['id']}&search=nomatch&status=completed&offset=5"):
        body = _overview(client, headers, query)
        assert (body["items"], body["total"]) == ([list_row], 1)
        assert body["counts_by_status"] == {**NO_STATUSES, "failed": 1}


def test_unknown_id_is_404(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    response = client.get(f"{OVERVIEW}?id={uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Source not found"


def test_other_organizations_id_is_404(client: TestClient, register_org) -> None:
    mine, theirs = register_org()["headers"], register_org()["headers"]
    their_source = _source(client, theirs, "Theirs")
    assert client.get(f"{OVERVIEW}?id={their_source['id']}", headers=mine).status_code == 404


def test_without_id_the_list_is_unchanged(client: TestClient, register_org) -> None:
    # Regression guard for the id filter: passes before and after it by design.
    headers = register_org()["headers"]
    _source(client, headers, "A")
    _source(client, headers, "B")
    body = _overview(client, headers, "?sort=name")
    assert (_titles(body), body["total"], body["offset"]) == (["A", "B"], 2, 0)


@pytest.mark.parametrize("query", ["?sort=published_at", "?status=archived", "?limit=0", "?limit=101", "?id=not-a-uuid"])
def test_invalid_parameters_are_rejected(client: TestClient, register_org, query: str) -> None:
    headers = register_org()["headers"]
    assert client.get(OVERVIEW + query, headers=headers).status_code == 422
