"""Settings persistence (REQ-SET-001): UI -> API -> DB -> reload."""
from fastapi.testclient import TestClient

P = "/api/v1/users/me/preferences"


def test_defaults_are_honestly_unpersisted(client: TestClient, register_org) -> None:
    org = register_org()
    r = client.get(P, headers=org["headers"]).json()
    assert r["persisted"] is False and r["language"] == "en" and r["theme"] == "system"


def test_preferences_persist_and_merge(client: TestClient, register_org) -> None:
    org = register_org()
    r = client.put(P, headers=org["headers"], json={"language": "fa", "theme": "dark"}).json()
    assert r["persisted"] and r["language"] == "fa" and r["theme"] == "dark"
    client.put(P, headers=org["headers"], json={"notifications": {"weekly_summary": False}})
    again = client.get(P, headers=org["headers"]).json()
    assert again["language"] == "fa" and again["theme"] == "dark"            # untouched fields kept
    assert again["notifications"]["weekly_summary"] is False and again["notifications"]["security_alerts"] is True


def test_invalid_values_are_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    assert client.put(P, headers=org["headers"], json={"language": "de"}).status_code == 422
    assert client.put(P, headers=org["headers"], json={"theme": "neon"}).status_code == 422
    assert client.put(P, headers=org["headers"], json={"notifications": {"marketing_spam": True}}).status_code == 422


def test_preferences_are_per_user_and_per_tenant(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    client.put(P, headers=a["headers"], json={"theme": "dark"})
    assert client.get(P, headers=b["headers"]).json()["theme"] == "system"


def test_preferences_require_authentication(client: TestClient) -> None:
    assert client.get(P).status_code == 401
