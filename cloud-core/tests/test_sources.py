"""
Integration tests for Source CRUD and authorization.
"""

from fastapi.testclient import TestClient


def test_create_source(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/sources",
        json={
            "source_type": "scientific_paper",
            "title": "A Study on Taranjabin",
            "doi": "10.1234/example",
            "reliability_score": 0.8,
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source_type"] == "scientific_paper"
    assert body["access_status"] == "unknown"
    assert body["rights_status"] == "unknown"
    assert body["reliability_score"] == 0.8
    assert body["metadata"] == {}


def test_create_source_with_metadata(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/sources",
        json={
            "source_type": "website",
            "title": "Some Blog Post",
            "metadata": {"crawled_at": "2026-01-01", "confidence": "low"},
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    assert response.json()["metadata"] == {"crawled_at": "2026-01-01", "confidence": "low"}


def test_viewer_cannot_create_source(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={
            "email": "source-viewer@example.dev", "name": "Viewer",
            "password": "supersecret123", "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "source-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/sources",
        json={"source_type": "website", "title": "Nope"},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_get_unknown_source_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/sources/00000000-0000-0000-0000-000000000000", headers=org["headers"]
    )
    assert response.status_code == 404


def test_update_source_access_status(client: TestClient, register_org) -> None:
    org = register_org()
    source = client.post(
        "/api/v1/sources",
        json={"source_type": "pdf", "title": "Some Paper"},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/sources/{source['id']}",
        json={"access_status": "paywalled", "reliability_score": 0.6},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_status"] == "paywalled"
    assert body["reliability_score"] == 0.6


def test_list_sources_filtered_by_type(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/sources", json={"source_type": "book", "title": "Book One"}, headers=org["headers"]
    )
    client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "Site One"}, headers=org["headers"]
    )

    response = client.get("/api/v1/sources?source_type=book", headers=org["headers"])
    assert response.status_code == 200
    assert all(item["source_type"] == "book" for item in response.json()["items"])


def test_reliability_score_out_of_range_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/sources",
        json={"source_type": "book", "title": "X", "reliability_score": 1.5},
        headers=org["headers"],
    )
    assert response.status_code == 422
