"""DELETE /sources/{id} (V5-source-detail-delete): owner/admin only; refused while evidence, publication citations or
research dependencies use the source; otherwise the source and its documents go, and the deletion is audit-logged."""
from fastapi.testclient import TestClient
from sqlalchemy import text


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    r = client.post(path, json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_an_unused_source_is_deleted_and_audit_logged(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    s = _post(client, org["headers"], "/api/v1/sources", {"source_type": "website", "title": "Old page"})
    r = client.delete(f"/api/v1/sources/{s['id']}", headers=org["headers"])
    assert r.status_code == 204, r.text
    assert client.get(f"/api/v1/sources/{s['id']}", headers=org["headers"]).status_code == 404
    assert db_session.execute(text("SELECT old_value->>'title' FROM audit_logs WHERE action = 'source.deleted' AND resource_id = :s"),
                              {"s": s["id"]}).scalar_one() == "Old page"


def test_a_source_with_evidence_is_refused_with_the_counts(client: TestClient, register_org) -> None:
    org = register_org()
    s = _post(client, org["headers"], "/api/v1/sources", {"source_type": "scientific_paper", "title": "Paper"})
    for _ in range(2):
        _post(client, org["headers"], "/api/v1/evidence", {"source_id": s["id"], "summary": "A finding."})
    r = client.delete(f"/api/v1/sources/{s['id']}", headers=org["headers"])
    assert r.status_code == 409
    assert "2 evidence records" in r.text
    assert client.get(f"/api/v1/sources/{s['id']}", headers=org["headers"]).status_code == 200


def test_another_organizations_source_is_not_found(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    s = _post(client, a["headers"], "/api/v1/sources", {"source_type": "website", "title": "Theirs"})
    assert client.delete(f"/api/v1/sources/{s['id']}", headers=b["headers"]).status_code == 404
    assert client.get(f"/api/v1/sources/{s['id']}", headers=a["headers"]).status_code == 200
