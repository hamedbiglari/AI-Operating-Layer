"""GET /visibility/aggregates (V5-visibility-detail-aggregates): the report's numbers in one call, counted, never
estimated; unknown actors and missing countries reported, not folded in; tenant-scoped; the window honoured."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"
CHATGPT_USER_UA = "Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
A = "/api/v1/visibility/aggregates"


def _event(**kw) -> dict:
    body = {"event_key": uuid.uuid4().hex, "occurred_at": datetime.now(UTC).isoformat(), "path": "/product/taranjabin",
            "user_agent": BROWSER_UA}
    body.update(kw)
    return body


def _ingest(client: TestClient, headers: dict, events: list[dict]) -> None:
    r = client.post("/api/v1/telemetry/ingest/page-views", json={"events": events}, headers=headers)
    assert r.status_code in (200, 201, 202), r.text


def _obs(client: TestClient, headers: dict, tested_at: datetime) -> None:
    r = client.post("/api/v1/visibility/observations", headers=headers, json={
        "platform": "chatgpt", "test_type": "brand_query", "prompt": "What is taranjabin?", "tested_at": tested_at.isoformat()})
    assert r.status_code == 201, r.text


def test_empty_organization_reports_zeros_and_nulls(client: TestClient, register_org) -> None:
    org = register_org()
    r = client.get(A, params={"days": 7}, headers=org["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform_observations"] == 0 and body["automated_requests"] == 0 and body["countries_reached"] == 0
    assert body["top_country"] is None and body["mean_dwell_ms"] is None and body["dwell_samples"] == 0
    assert len(body["by_day"]) in (7, 8) and all(d["requests"] == 0 and d["observations"] == 0 for d in body["by_day"])
    assert body["by_country"] == [] and body["top_pages"] == [] and body["by_actor_type"] == []


def test_aggregates_count_what_is_stored(client: TestClient, adapter_credential, register_org) -> None:
    org, adapter = adapter_credential["org"], adapter_credential["headers"]
    now = datetime.now(UTC)
    _ingest(client, adapter, [
        _event(user_agent=GPTBOT_UA, geo_method="edge_header", geo_country="ir", path="/product/taranjabin"),
        _event(user_agent=GPTBOT_UA, geo_method="edge_header", geo_country="ir", path="/product/taranjabin"),
        _event(user_agent=CHATGPT_USER_UA, geo_method="edge_header", geo_country="de", path="/product/saffron"),
        _event(user_agent=GPTBOT_UA, path="/blog/manna"),                                   # automated, no country
        _event(dwell_ms=4000, dwell_is_complete=True), _event(dwell_ms=6000, dwell_is_complete=True), _event(),  # people
        _event(user_agent=GPTBOT_UA, geo_method="edge_header", geo_country="fr",
               occurred_at=(now - timedelta(days=40)).isoformat()),                         # outside a 28-day window
    ])
    _obs(client, org["headers"], now)
    _obs(client, org["headers"], now - timedelta(days=2))
    _obs(client, org["headers"], now - timedelta(days=60))                                   # outside

    views = client.get("/api/v1/telemetry/page-views", params={"limit": 50}, headers=org["headers"]).json()["items"]
    types = sorted(v["actor_type"] for v in views)
    assert types.count("ai_crawler") == 4 and types.count("ai_user_agent") == 1 and types.count("human") == 3, types

    r = client.get(A, params={"days": 28}, headers=org["headers"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["days"] == 28
    assert b["platform_observations"] == 2
    assert b["automated_requests"] == 4                     # 3 GPTBot + 1 ChatGPT-User in the window; people excluded
    assert b["unclassified_requests"] == 0
    assert b["countries_reached"] == 2
    assert b["top_country"] == {"country": "IR", "requests": 2}
    assert b["by_country"] == [{"country": "IR", "requests": 2}, {"country": "DE", "requests": 1}]
    assert b["requests_without_country"] == 1
    assert b["mean_dwell_ms"] == 5000 and b["dwell_samples"] == 2   # the view with no time does not count as 0
    assert b["by_actor_type"] == [{"key": "ai_crawler", "requests": 3}, {"key": "ai_user_agent", "requests": 1}]
    assert b["top_pages"][0] == {"key": "/product/taranjabin", "requests": 2}
    assert sum(d["requests"] for d in b["by_day"]) == 4 and sum(d["observations"] for d in b["by_day"]) == 2
    today = next(d for d in b["by_day"] if d["day"] == now.date().isoformat())
    assert today["requests"] == 4 and today["observations"] == 1

    # A wider window reaches the older rows; a narrower one drops them.
    wide = client.get(A, params={"days": 90}, headers=org["headers"]).json()
    assert wide["automated_requests"] == 5 and wide["platform_observations"] == 3 and wide["countries_reached"] == 3
    assert client.get(A, params={"days": 1}, headers=org["headers"]).json()["platform_observations"] == 1

    # Tenant isolation: another organization sees none of it.
    other = register_org()
    assert client.get(A, headers=other["headers"]).json()["automated_requests"] == 0

    # Bounds.
    assert client.get(A, params={"days": 0}, headers=org["headers"]).status_code == 422
    assert client.get(A, params={"days": 491}, headers=org["headers"]).status_code == 422
    assert client.get(A).status_code == 401
