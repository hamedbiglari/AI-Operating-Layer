"""VPN / proxy advisory (login page): detects proxy headers, never blocks, never echoes the IP."""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings

P = "/api/v1/auth/network-check"


def test_direct_connection_is_not_suspected(client: TestClient) -> None:
    r = client.get(P).json()
    assert r["suspected"] is False and r["signals"] == [] and r["blocking"] is False and r["advice"] is None
    assert r["ip_reputation"] == "not_configured"


def test_proxy_headers_are_detected(client: TestClient) -> None:
    assert client.get(P, headers={"Via": "1.1 corp-proxy"}).json()["signals"] == ["via_header"]
    assert client.get(P, headers={"X-Forwarded-For": "203.0.113.9, 198.51.100.2"}).json()["signals"] == ["forwarded_chain"]
    assert client.get(P, headers={"Forwarded": "for=203.0.113.9"}).json()["signals"] == ["forwarded_chain"]
    r = client.get(P, headers={"X-Proxy-ID": "abc"}).json()
    assert r["suspected"] and r["signals"] == ["proxy_header"] and "VPN or proxy" in r["advice"]


def test_our_own_proxy_hops_are_not_counted(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    assert client.get(P, headers={"X-Forwarded-For": "203.0.113.9"}).json()["suspected"] is False
    assert client.get(P, headers={"X-Forwarded-For": "203.0.113.9, 198.51.100.2"}).json()["suspected"] is True


def test_the_ip_and_header_values_are_never_echoed(client: TestClient) -> None:
    text = client.get(P, headers={"X-Forwarded-For": "203.0.113.77, 198.51.100.2", "Via": "1.1 secret-proxy-name"}).text
    assert "203.0.113.77" not in text and "secret-proxy-name" not in text


def test_sign_up_still_works_behind_a_proxy(client: TestClient) -> None:
    assert client.get(P, headers={"Via": "1.1 corp-proxy"}).json()["blocking"] is False
    r = client.post("/api/v1/auth/register-organization", headers={"Via": "1.1 corp-proxy", "X-Forwarded-For": "203.0.113.9, 198.51.100.2"},
                    json={"organization_name": f"Proxy Org {uuid.uuid4().hex[:6]}", "owner_email": f"p{uuid.uuid4().hex[:6]}@x.example",
                          "owner_name": "P", "owner_password": "proxy-user-pass-1"})
    assert r.status_code == 201, r.text
