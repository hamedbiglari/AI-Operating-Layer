"""
Integration tests for Document CRUD, source ownership checks, content
hashing, and version bumping.
"""

from fastapi.testclient import TestClient


def _create_source(client: TestClient, headers: dict, title: str = "A Source") -> dict:
    return client.post(
        "/api/v1/sources",
        json={"source_type": "website", "title": title},
        headers=headers,
    ).json()


def test_create_document_under_source(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])

    response = client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": "Doc 1", "content": "Some extracted text."},
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source_id"] == source["id"]
    assert body["version"] == 1
    assert body["extraction_status"] == "pending"
    assert body["content_hash"] is not None
    assert body["file_size"] == len("Some extracted text.".encode("utf-8"))


def test_create_document_under_nonexistent_source_returns_404(
    client: TestClient, register_org
) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/documents?source_id=00000000-0000-0000-0000-000000000000",
        json={"title": "Doc", "content": "x"},
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_create_document_with_no_content_has_null_hash(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    response = client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": "Empty Doc"},
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content"] is None
    assert body["content_hash"] is None
    assert body["file_size"] is None


def test_update_content_bumps_version_and_rehashes(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    doc = client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": "Doc", "content": "version one"},
        headers=org["headers"],
    ).json()
    original_hash = doc["content_hash"]

    response = client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"content": "version two, completely different"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["content_hash"] != original_hash
    assert body["extraction_status"] == "pending"


def test_updating_content_deletes_stale_chunks(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    doc = client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": "Doc", "content": "Original content about taranjabin."},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    chunks_before = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks_before["total"] == 1

    client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"content": "Completely different content now."},
        headers=org["headers"],
    )
    chunks_after = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks_after["total"] == 0


def test_list_documents_filtered_by_source(client: TestClient, register_org) -> None:
    org = register_org()
    source_a = _create_source(client, org["headers"], "Source A")
    source_b = _create_source(client, org["headers"], "Source B")
    client.post(
        f"/api/v1/documents?source_id={source_a['id']}",
        json={"title": "From A"}, headers=org["headers"],
    )
    client.post(
        f"/api/v1/documents?source_id={source_b['id']}",
        json={"title": "From B"}, headers=org["headers"],
    )

    response = client.get(f"/api/v1/documents?source_id={source_a['id']}", headers=org["headers"])
    titles = [d["title"] for d in response.json()["items"]]
    assert titles == ["From A"]

    via_nested = client.get(f"/api/v1/sources/{source_a['id']}/documents", headers=org["headers"])
    assert [d["title"] for d in via_nested.json()["items"]] == ["From A"]


def test_viewer_cannot_create_document(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    client.post(
        "/api/v1/users",
        json={
            "email": "doc-viewer@example.dev", "name": "Viewer",
            "password": "supersecret123", "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "doc-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": "Nope"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
