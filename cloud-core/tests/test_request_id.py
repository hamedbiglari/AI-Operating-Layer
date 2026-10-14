"""
Unit tests for request-id sanitization. No database required.
"""

from fastapi.testclient import TestClient


def test_valid_request_id_is_echoed_back(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123_XYZ"})
    assert response.headers["X-Request-ID"] == "abc-123_XYZ"


def test_oversized_request_id_is_replaced(raw_client: TestClient) -> None:
    oversized = "a" * 500
    response = raw_client.get("/api/v1/health/live", headers={"X-Request-ID": oversized})
    returned = response.headers["X-Request-ID"]
    assert returned != oversized
    assert len(returned) <= 64


def test_request_id_with_invalid_characters_is_replaced(raw_client: TestClient) -> None:
    malicious = "abc\r\nX-Injected-Header: evil"
    response = raw_client.get("/api/v1/health/live", headers={"X-Request-ID": malicious})
    returned = response.headers["X-Request-ID"]
    assert returned != malicious
    assert "\r" not in returned and "\n" not in returned


def test_missing_request_id_generates_one(raw_client: TestClient) -> None:
    response = raw_client.get("/api/v1/health/live")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0
