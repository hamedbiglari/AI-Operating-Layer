"""Archive and unarchive sources (V5-source-detail-archive, V5-source-archive-state; migration 0056).

Archived sources leave the lists (GET /sources, /sources/overview, the CSV export) unless include_archived=true; the
detail (overview ?id= and GET /sources/{id}) still works; owner/admin only; both directions are audit-logged."""
from fastapi.testclient import TestClient
from sqlalchemy import text


def _source(client: TestClient, headers: dict, title: str) -> dict:
    r = client.post("/api/v1/sources", json={"source_type": "website", "title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _titles(client: TestClient, headers: dict, path: str) -> list[str]:
    return sorted(x["title"] for x in client.get(path, headers=headers).json()["items"])


def test_archive_hides_the_source_from_the_lists_and_unarchive_brings_it_back(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    old, keep = _source(client, org["headers"], "Old page"), _source(client, org["headers"], "Keep")
    r = client.post(f"/api/v1/sources/{old['id']}/archive", json={"reason": "  Superseded by the 2026 review.  "}, headers=org["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_archived"] is True and body["archived_at"] and body["archive_reason"] == "Superseded by the 2026 review."
    for path in ("/api/v1/sources", "/api/v1/sources/overview"):
        assert _titles(client, org["headers"], path) == ["Keep"]
        assert _titles(client, org["headers"], path + "?include_archived=true") == ["Keep", "Old page"]
    rows = {x["title"]: x["is_archived"] for x in client.get("/api/v1/sources/overview?include_archived=true", headers=org["headers"]).json()["items"]}
    assert rows == {"Keep": False, "Old page": True}
    assert "Old page" not in client.get("/api/v1/sources/export.csv", headers=org["headers"]).text
    assert "Old page" in client.get("/api/v1/sources/export.csv?include_archived=true", headers=org["headers"]).text

    r = client.post(f"/api/v1/sources/{old['id']}/unarchive", headers=org["headers"])
    assert r.status_code == 200 and r.json()["is_archived"] is False and r.json()["archive_reason"] is None
    assert _titles(client, org["headers"], "/api/v1/sources/overview") == ["Keep", "Old page"]
    actions = db_session.execute(text("SELECT action FROM audit_logs WHERE resource_id = :s AND action LIKE 'source.%archived' ORDER BY created_at"),
                                 {"s": old["id"]}).scalars().all()
    assert actions == ["source.archived", "source.unarchived"]


def test_an_archived_source_still_opens(client: TestClient, register_org) -> None:
    org = register_org()
    s = _source(client, org["headers"], "Archived paper")
    client.post(f"/api/v1/sources/{s['id']}/archive", headers=org["headers"])
    one = client.get(f"/api/v1/sources/overview?id={s['id']}", headers=org["headers"]).json()
    assert one["total"] == 1 and one["items"][0]["is_archived"] is True
    assert client.get(f"/api/v1/sources/{s['id']}", headers=org["headers"]).json()["is_archived"] is True


def test_archiving_twice_keeps_the_first_date(client: TestClient, register_org) -> None:
    org = register_org()
    s = _source(client, org["headers"], "Twice")
    first = client.post(f"/api/v1/sources/{s['id']}/archive", headers=org["headers"]).json()["archived_at"]
    again = client.post(f"/api/v1/sources/{s['id']}/archive", json={"reason": "later"}, headers=org["headers"]).json()
    assert again["archived_at"] == first and again["archive_reason"] == "later"


def test_another_organizations_source_is_not_found(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    s = _source(client, a["headers"], "Theirs")
    assert client.post(f"/api/v1/sources/{s['id']}/archive", headers=b["headers"]).status_code == 404
    assert client.post(f"/api/v1/sources/{s['id']}/unarchive", headers=b["headers"]).status_code == 404


def test_an_editor_cannot_archive(client: TestClient, register_org) -> None:
    import uuid

    org = register_org()
    s = _source(client, org["headers"], "Editor try")
    email = f"editor-{uuid.uuid4().hex[:8]}@example.dev"
    client.post("/api/v1/users", json={"email": email, "name": "E", "password": "supersecret123", "role": "editor"}, headers=org["headers"])
    token = client.post("/api/v1/auth/login", data={"username": email, "password": "supersecret123"}).json()["access_token"]
    editor = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/api/v1/sources/{s['id']}/archive", headers=editor).status_code == 403
    assert client.post(f"/api/v1/sources/{s['id']}/unarchive", headers=editor).status_code == 403
