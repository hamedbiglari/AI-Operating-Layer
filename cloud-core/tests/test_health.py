"""
Health endpoint tests. Uses `raw_client` (no DB override) intentionally:
these must behave sensibly whether or not Postgres is reachable, which
is the entire point of splitting liveness from readiness.
"""

from fastapi.testclient import TestClient


def test_root_endpoint(raw_client: TestClient) -> None:
    response = raw_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "service" in body
    assert "api" in body


def test_liveness_never_touches_database(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "database" not in body


def test_readiness_reports_database_status(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body
    if body["status"] == "degraded":
        assert response.status_code == 503


def test_legacy_health_alias_matches_readiness(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "database" in body


def test_health_endpoint_sets_request_id_header(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health/live")
    assert "X-Request-ID" in response.headers
