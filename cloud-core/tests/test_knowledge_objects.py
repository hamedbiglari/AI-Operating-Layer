"""
Integration tests for Knowledge Objects: CRUD, publish lifecycle,
automatic versioning, search/filter, and role-based authorization.
"""

from fastapi.testclient import TestClient


def _create_ko(client: TestClient, headers: dict, **overrides) -> dict:
    payload = {
        "canonical_name": "Taranjabin",
        "object_type": "plant",
        "description": "A manna-like exudate used in traditional Persian medicine.",
        "language": "fa",
    }
    payload.update(overrides)
    response = client.post("/api/v1/knowledge", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_editor_can_create_knowledge_object(client: TestClient, register_org) -> None:
    org = register_org()
    body = _create_ko(client, org["headers"])
    assert body["canonical_name"] == "Taranjabin"
    assert body["slug"] == "taranjabin"
    assert body["status"] == "draft"
    assert body["public_visibility"] is False
    assert body["ai_visibility"] is False
    assert body["version"] == 1


def test_slug_is_auto_generated_and_deduplicated(client: TestClient, register_org) -> None:
    org = register_org()
    first = _create_ko(client, org["headers"])
    second = _create_ko(client, org["headers"])
    assert first["slug"] == "taranjabin"
    assert second["slug"] == "taranjabin-2"


def test_viewer_cannot_create_knowledge_object(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "ko-viewer@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "ko-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Should Fail", "object_type": "plant"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_researcher_can_create_knowledge_object(client: TestClient, register_org) -> None:
    """RESEARCHER is a knowledge-editor role even though it's not an
    ADMIN_ROLES member — this is the whole point of KNOWLEDGE_EDITOR_ROLES
    being a separate authorization set from organization/user management."""
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "researcher@example.dev",
            "name": "Researcher",
            "password": "supersecret123",
            "role": "researcher",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "researcher@example.dev", "password": "supersecret123"},
    )
    researcher_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Researcher Made This", "object_type": "compound"},
        headers=researcher_headers,
    )
    assert response.status_code == 201


def test_get_unknown_knowledge_object_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/knowledge/00000000-0000-0000-0000-000000000000", headers=org["headers"]
    )
    assert response.status_code == 404


def test_update_creates_new_version_and_bumps_version_number(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    assert ko["version"] == 1

    response = client.patch(
        f"/api/v1/knowledge/{ko['id']}",
        json={"description": "Updated description.", "change_summary": "Clarified description"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["version"] == 2
    assert updated["description"] == "Updated description."

    versions = client.get(f"/api/v1/knowledge/{ko['id']}/versions", headers=org["headers"]).json()
    assert len(versions) == 2
    assert versions[0]["version"] == 2  # most recent first
    assert versions[0]["change_summary"] == "Clarified description"
    assert versions[1]["version"] == 1
    assert versions[1]["change_summary"] == "Created"


def test_publish_sets_status_and_public_visibility(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    assert ko["status"] == "draft"

    response = client.post(f"/api/v1/knowledge/{ko['id']}/publish", headers=org["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    assert body["public_visibility"] is True
    assert body["version"] == 2  # publish is itself a versioned change


def test_archive_via_delete_is_soft(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])

    response = client.delete(f"/api/v1/knowledge/{ko['id']}", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == "archived"

    # Still readable — this is a soft delete.
    get_response = client.get(f"/api/v1/knowledge/{ko['id']}", headers=org["headers"])
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "archived"


def test_search_matches_canonical_name(client: TestClient, register_org) -> None:
    org = register_org()
    _create_ko(client, org["headers"], canonical_name="Taranjabin", object_type="plant")
    _create_ko(client, org["headers"], canonical_name="Turmeric", object_type="plant")

    response = client.get("/api/v1/knowledge/search?q=Taran", headers=org["headers"])
    assert response.status_code == 200
    names = [item["canonical_name"] for item in response.json()["items"]]
    assert "Taranjabin" in names
    assert "Turmeric" not in names


def test_filter_by_object_type_and_status(client: TestClient, register_org) -> None:
    org = register_org()
    plant = _create_ko(client, org["headers"], canonical_name="Plant One", object_type="plant")
    _create_ko(client, org["headers"], canonical_name="Compound One", object_type="compound")
    client.post(f"/api/v1/knowledge/{plant['id']}/publish", headers=org["headers"])

    by_type = client.get("/api/v1/knowledge?object_type=compound", headers=org["headers"]).json()
    assert all(item["object_type"] == "compound" for item in by_type["items"])

    by_status = client.get("/api/v1/knowledge?status=published", headers=org["headers"]).json()
    assert all(item["status"] == "published" for item in by_status["items"])
    assert any(item["id"] == plant["id"] for item in by_status["items"])
