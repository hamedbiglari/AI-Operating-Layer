"""
Integration tests for Knowledge Gaps.
"""

from fastapi.testclient import TestClient


def _create_ko(client: TestClient, headers: dict) -> dict:
    return client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=headers,
    ).json()


def test_create_knowledge_gap(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])

    response = client.post(
        "/api/v1/knowledge-gaps",
        json={
            "knowledge_object_id": ko["id"],
            "gap_type": "evidence_gap",
            "description": "No clinical evidence found yet for the digestive-aid claim.",
            "priority": "high",
            "recommended_action": "search_clinical_database",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["gap_type"] == "evidence_gap"
    assert body["status"] == "open"
    assert body["priority"] == "high"


def test_create_gap_under_nonexistent_knowledge_object_returns_404(
    client: TestClient, register_org
) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/knowledge-gaps",
        json={
            "knowledge_object_id": "00000000-0000-0000-0000-000000000000",
            "gap_type": "content_gap",
            "description": "N/A",
        },
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_update_gap_status_lifecycle(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    gap = client.post(
        "/api/v1/knowledge-gaps",
        json={
            "knowledge_object_id": ko["id"],
            "gap_type": "source_gap",
            "description": "Missing an authoritative source for origin.",
        },
        headers=org["headers"],
    ).json()
    assert gap["status"] == "open"

    in_progress = client.patch(
        f"/api/v1/knowledge-gaps/{gap['id']}",
        json={"status": "in_progress"},
        headers=org["headers"],
    )
    assert in_progress.json()["status"] == "in_progress"

    resolved = client.patch(
        f"/api/v1/knowledge-gaps/{gap['id']}",
        json={"status": "resolved"},
        headers=org["headers"],
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_list_gaps_filtered_by_status_and_knowledge_object(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    gap = client.post(
        "/api/v1/knowledge-gaps",
        json={
            "knowledge_object_id": ko["id"],
            "gap_type": "claim_gap",
            "description": "Need more claims about safe dosage.",
        },
        headers=org["headers"],
    ).json()

    via_nested = client.get(
        f"/api/v1/knowledge/{ko['id']}/gaps", headers=org["headers"]
    ).json()
    assert any(g["id"] == gap["id"] for g in via_nested["items"])

    via_status = client.get(
        "/api/v1/knowledge-gaps?status=open", headers=org["headers"]
    ).json()
    assert any(g["id"] == gap["id"] for g in via_status["items"])


def test_viewer_cannot_create_gap(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _create_ko(client, org["headers"])
    client.post(
        "/api/v1/users",
        json={
            "email": "gap-viewer@example.dev", "name": "Viewer",
            "password": "supersecret123", "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "gap-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko["id"], "gap_type": "content_gap", "description": "Nope"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
