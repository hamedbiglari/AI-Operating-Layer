"""
Integration tests for ResearchProject: creation across all four modes,
the GAP_DRIVEN-requires-a-gap validation rule, and the validated
lifecycle transition table.
"""

from fastapi.testclient import TestClient


def _create_ko(client: TestClient, headers: dict) -> dict:
    return client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"}, headers=headers
    ).json()


def _create_gap(client: TestClient, headers: dict) -> dict:
    ko = _create_ko(client, headers)
    return client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko["id"], "gap_type": "evidence_gap", "description": "Missing evidence."},
        headers=headers,
    ).json()


def test_create_exploratory_project_without_gap(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/research/projects",
        json={"name": "Taranjabin sweetness", "objective": "Understand why it tastes sweet.", "mode": "exploratory"},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "exploratory"
    assert body["status"] == "draft"
    assert body["knowledge_gap_id"] is None


def test_gap_driven_project_requires_a_gap(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/research/projects",
        json={"name": "Fill the gap", "objective": "x", "mode": "gap_driven"},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_gap_driven_project_with_gap_succeeds(client: TestClient, register_org) -> None:
    org = register_org()
    gap = _create_gap(client, org["headers"])

    response = client.post(
        "/api/v1/research/projects",
        json={
            "name": "Fill the gap",
            "objective": "Find clinical evidence.",
            "mode": "gap_driven",
            "knowledge_gap_id": gap["id"],
        },
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["knowledge_gap_id"] == gap["id"]


def test_gap_driven_project_rejects_another_orgs_gap(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    gap_b = _create_gap(client, org_b["headers"])

    response = client.post(
        "/api/v1/research/projects",
        json={
            "name": "Smuggled gap",
            "objective": "x",
            "mode": "gap_driven",
            "knowledge_gap_id": gap_b["id"],
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_update_project_name_and_objective(client: TestClient, register_org) -> None:
    org = register_org()
    project = client.post(
        "/api/v1/research/projects",
        json={"name": "Old name", "objective": "Old objective.", "mode": "exploratory"},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/research/projects/{project['id']}",
        json={"name": "New name"},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "New name"
    assert body["objective"] == "Old objective."


def test_valid_transition_draft_to_active_to_completed_to_archived(client: TestClient, register_org) -> None:
    org = register_org()
    project = client.post(
        "/api/v1/research/projects",
        json={"name": "P", "objective": "x", "mode": "user_driven"},
        headers=org["headers"],
    ).json()
    assert project["status"] == "draft"

    active = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "active"}, headers=org["headers"]
    )
    assert active.status_code == 200
    assert active.json()["status"] == "active"

    completed = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "completed"}, headers=org["headers"]
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    archived = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "archived"}, headers=org["headers"]
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_invalid_transition_draft_to_completed_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    project = client.post(
        "/api/v1/research/projects",
        json={"name": "P", "objective": "x", "mode": "user_driven"},
        headers=org["headers"],
    ).json()

    response = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "completed"}, headers=org["headers"]
    )
    assert response.status_code == 422


def test_archived_is_terminal(client: TestClient, register_org) -> None:
    org = register_org()
    project = client.post(
        "/api/v1/research/projects",
        json={"name": "P", "objective": "x", "mode": "user_driven"},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/research/projects/{project['id']}/transition", json={"status": "cancelled"}, headers=org["headers"])
    archived = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "archived"}, headers=org["headers"]
    ).json()
    assert archived["status"] == "archived"

    response = client.post(
        f"/api/v1/research/projects/{project['id']}/transition", json={"status": "active"}, headers=org["headers"]
    )
    assert response.status_code == 422


def test_list_projects_filtered_by_mode_and_status(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/research/projects",
        json={"name": "Exploratory one", "objective": "x", "mode": "exploratory"},
        headers=org["headers"],
    )
    continuous = client.post(
        "/api/v1/research/projects",
        json={"name": "Continuous one", "objective": "x", "mode": "continuous"},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/research/projects/{continuous['id']}/transition", json={"status": "active"}, headers=org["headers"])

    by_mode = client.get("/api/v1/research/projects?mode=continuous", headers=org["headers"]).json()
    assert all(p["mode"] == "continuous" for p in by_mode["items"])
    assert any(p["id"] == continuous["id"] for p in by_mode["items"])

    by_status = client.get("/api/v1/research/projects?status=active", headers=org["headers"]).json()
    assert any(p["id"] == continuous["id"] for p in by_status["items"])


def test_viewer_cannot_create_research_project(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={"email": "research-viewer@example.dev", "name": "Viewer", "password": "supersecret123", "role": "viewer"},
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login", data={"username": "research-viewer@example.dev", "password": "supersecret123"}
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/research/projects",
        json={"name": "Nope", "objective": "x", "mode": "exploratory"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_get_unknown_project_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/research/projects/00000000-0000-0000-0000-000000000000", headers=org["headers"]
    )
    assert response.status_code == 404
