"""
Integration tests for Entities.
"""

from fastapi.testclient import TestClient


def _create_ko(client: TestClient, headers: dict, name: str = "Taranjabin") -> dict:
    response = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": name, "object_type": "plant"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_entity_under_knowledge_object(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])

    response = client.post(
        "/api/v1/entities",
        json={
            "knowledge_object_id": ko["id"],
            "entity_type": "plant",
            "canonical_name": "Taranjabin",
            "aliases": ["Persian Manna"],
            "external_ids": {"wikidata": "Q123456"},
            "language": "fa",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["knowledge_object_id"] == ko["id"]
    assert body["aliases"] == ["Persian Manna"]
    assert body["external_ids"] == {"wikidata": "Q123456"}


def test_create_entity_under_nonexistent_knowledge_object_returns_404(
    client: TestClient, register_org
) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/entities",
        json={
            "knowledge_object_id": "00000000-0000-0000-0000-000000000000",
            "entity_type": "plant",
            "canonical_name": "Ghost",
        },
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_list_entities_filtered_by_knowledge_object(client: TestClient, register_org) -> None:
    org = register_org()
    ko_a = _create_ko(client, org["headers"], "Object A")
    ko_b = _create_ko(client, org["headers"], "Object B")

    client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko_a["id"], "entity_type": "plant", "canonical_name": "Entity A"},
        headers=org["headers"],
    )
    client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko_b["id"], "entity_type": "plant", "canonical_name": "Entity B"},
        headers=org["headers"],
    )

    response = client.get(
        f"/api/v1/entities?knowledge_object_id={ko_a['id']}", headers=org["headers"]
    )
    names = [item["canonical_name"] for item in response.json()["items"]]
    assert names == ["Entity A"]

    via_nested_route = client.get(
        f"/api/v1/knowledge/{ko_a['id']}/entities", headers=org["headers"]
    )
    assert [i["canonical_name"] for i in via_nested_route.json()["items"]] == ["Entity A"]


def test_update_entity(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    entity = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Old Name"},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={"canonical_name": "New Name", "aliases": ["alt1"]},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_name"] == "New Name"
    assert body["aliases"] == ["alt1"]


def test_viewer_cannot_create_entity(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    client.post(
        "/api/v1/users",
        json={
            "email": "entity-viewer@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "entity-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Nope"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_get_unknown_entity_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/entities/00000000-0000-0000-0000-000000000000", headers=org["headers"]
    )
    assert response.status_code == 404
