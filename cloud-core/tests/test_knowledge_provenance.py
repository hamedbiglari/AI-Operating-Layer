"""
Integration tests for GET /knowledge/{id}/provenance. Claims, links, evidence,
sources and documents are created through the API; evidence basis and
subject_tested, and document conversions, have no API that sets them, so they
are written to the database.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event, update

from app.models.document_artifact import DocumentConversion
from app.models.enums import DocumentConversionStatus
from app.models.evidence import Evidence


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _ko(client: TestClient, headers: dict) -> tuple[dict, dict]:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": "Taranjabin", "object_type": "plant"})
    subject = _post(client, headers, "/api/v1/entities",
                    {"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"})
    return ko, subject


def _claim(client: TestClient, headers: dict, ko: dict, subject: dict, value: str) -> dict:
    return _post(client, headers, "/api/v1/claims", {"knowledge_object_id": ko["id"], "subject_entity_id": subject["id"],
                                                      "predicate": "contains", "object_value": value})


def _evidence(client: TestClient, headers: dict, source: dict, document: dict | None = None) -> dict:
    body = {"source_id": source["id"], "summary": "A finding."}
    if document:
        body["document_id"] = document["id"]
    return _post(client, headers, "/api/v1/evidence", body)


def _link(client: TestClient, headers: dict, claim: dict, evidence: dict, relation: str = "supports") -> dict:
    return _post(client, headers, "/api/v1/claim-evidence",
                 {"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": relation})


def _get(client: TestClient, headers: dict, ko: dict, query: str = ""):
    return client.get(f"/api/v1/knowledge/{ko['id']}/provenance{query}", headers=headers)


def test_query_count_does_not_grow_with_claims_or_links(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    small, small_subject = _ko(client, headers)
    large, large_subject = _ko(client, headers)
    source = _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": "S"})
    document = _post(client, headers, f"/api/v1/documents?source_id={source['id']}", {"title": "D", "content": "t"})
    _link(client, headers, _claim(client, headers, small, small_subject, "a"), _evidence(client, headers, source, document))
    for value in ("a", "b", "c", "d"):
        claim = _claim(client, headers, large, large_subject, value)
        for _ in range(3):
            other = _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": "S"})
            doc = _post(client, headers, f"/api/v1/documents?source_id={other['id']}", {"title": "D", "content": "t"})
            _link(client, headers, claim, _evidence(client, headers, other, doc))

    def count(ko: dict) -> int:
        queries = []
        listener = lambda conn, cursor, stmt, *a: queries.append(stmt)
        event.listen(db_session.get_bind(), "before_cursor_execute", listener)
        try:
            assert _get(client, headers, ko).status_code == 200
        finally:
            event.remove(db_session.get_bind(), "before_cursor_execute", listener)
        return len(queries)

    assert count(large) == count(small)
    body = _get(client, headers, large).json()
    assert (len(body["claims"]), len(body["evidence"]), len(body["sources"]), len(body["documents"])) == (4, 12, 12, 12)


def test_happy_path_fills_the_maps(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    ko, subject = _ko(client, headers)
    claim = _claim(client, headers, ko, subject, "mannitol")
    review = _post(client, headers, "/api/v1/sources",
                   {"source_type": "scientific_paper", "title": "Review 2025", "doi": "10.1/x"})
    survey = _post(client, headers, "/api/v1/sources", {"source_type": "scientific_paper", "title": "Survey 2023"})
    converted = _post(client, headers, f"/api/v1/documents?source_id={review['id']}", {"title": "Paper", "content": "t"})
    plain = _post(client, headers, f"/api/v1/documents?source_id={survey['id']}", {"title": "Notes", "content": "t"})
    db_session.add(DocumentConversion(
        organization_id=uuid.UUID(converted["organization_id"]), document_id=uuid.UUID(converted["id"]),
        original_filename="p.pdf", source_hash="0" * 64, source_size_bytes=1, source_mime_type="application/pdf",
        converter_name="markitdown", converter_version="0.1.7", conversion_status=DocumentConversionStatus.SUCCEEDED,
    ))
    supporting = _evidence(client, headers, review, converted)
    against = _evidence(client, headers, survey, plain)
    db_session.execute(update(Evidence).where(Evidence.id == uuid.UUID(supporting["id"]))
                       .values(basis="abstract", subject_tested="Alhagi maurorum"))
    db_session.flush()
    link_a = _link(client, headers, claim, supporting)
    link_b = _link(client, headers, claim, against, "contradicts")

    response = _get(client, headers, ko)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["knowledge_object"] == {"id": ko["id"], "canonical_name": "Taranjabin", "status": ko["status"]}
    assert (body["total_claims"], body["total_evidence"]) == (1, 2)
    [read] = body["claims"]
    assert (read["id"], read["text"], read["predicate"], read["object_value"]) == (
        claim["id"], "contains mannitol", "contains", "mannitol")
    assert (read["status"], read["evidence_strength"]) == (claim["status"], claim["evidence_strength"])
    assert read["links"] == [
        {"link_id": link_a["id"], "evidence_id": supporting["id"], "relation": "supports", "weight": None},
        {"link_id": link_b["id"], "evidence_id": against["id"], "relation": "contradicts", "weight": None},
    ]

    assert set(body["evidence"]) == {supporting["id"], against["id"]}
    ev = body["evidence"][supporting["id"]]
    assert (ev["basis"], ev["subject_tested"]) == ("abstract", "Alhagi maurorum")
    assert (ev["source_id"], ev["document_id"]) == (review["id"], converted["id"])
    assert body["evidence"][against["id"]]["basis"] is None

    assert set(body["sources"]) == {review["id"], survey["id"]}
    assert body["sources"][review["id"]] == {"id": review["id"], "title": "Review 2025", "doi": "10.1/x",
                                             "full_text_accessed": False}
    assert body["documents"][converted["id"]] == {"id": converted["id"], "title": "Paper",
                                                  "mime_type": converted["mime_type"], "converter_version": "0.1.7"}
    assert body["documents"][plain["id"]]["converter_version"] is None


def test_claims_are_paged(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    ko, subject = _ko(client, headers)
    source = _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": "S"})
    for value in ("a", "b", "c"):
        _link(client, headers, _claim(client, headers, ko, subject, value), _evidence(client, headers, source))

    body = _get(client, headers, ko, "?limit=2&offset=0").json()

    assert (body["total_claims"], len(body["claims"])) == (3, 2)
    # total_evidence counts the page's evidence only.
    assert body["total_evidence"] == 2


def test_other_organization_gets_404(client: TestClient, register_org) -> None:
    owner = register_org()["headers"]
    ko, _ = _ko(client, owner)

    response = _get(client, register_org()["headers"], ko)

    assert response.status_code == 404
