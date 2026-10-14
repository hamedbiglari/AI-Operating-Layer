"""
Integration tests for /queries/{id}/classify, /queries/{id}/intents,
and the auto DISCOVERED -> CLASSIFIED transition this drives (never a
manual PATCH target — see Query's model docstring).
"""

import json

from fastapi.testclient import TestClient


def _import_one(client: TestClient, headers: dict, text: str) -> dict:
    response = client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": json.dumps([{"query": text}])},
        headers=headers,
    )
    return response.json()["items"][0]


def test_classify_creates_intent_and_transitions_query_status(client: TestClient, register_org) -> None:
    org = register_org()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")
    assert client.get(f"/api/v1/queries/{query['query_id']}", headers=org["headers"]).json()["status"] == "discovered"

    response = client.post(f"/api/v1/queries/{query['query_id']}/classify", headers=org["headers"])
    assert response.status_code == 200, response.text
    intents = response.json()
    assert len(intents) >= 1
    assert any(i["intent_type"] == "price" for i in intents)
    assert sum(1 for i in intents if i["is_primary"]) == 1

    refreshed = client.get(f"/api/v1/queries/{query['query_id']}", headers=org["headers"]).json()
    assert refreshed["status"] == "classified"


def test_classify_with_no_rule_match_leaves_query_discovered(client: TestClient, register_org) -> None:
    org = register_org()
    query = _import_one(client, org["headers"], "زضصثقفغعهخحجچ")

    response = client.post(f"/api/v1/queries/{query['query_id']}/classify", headers=org["headers"])
    assert response.status_code == 200
    assert response.json() == []

    refreshed = client.get(f"/api/v1/queries/{query['query_id']}", headers=org["headers"]).json()
    assert refreshed["status"] == "discovered"


def test_classify_is_idempotent_no_duplicate_intent_types(client: TestClient, register_org) -> None:
    org = register_org()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")
    first = client.post(f"/api/v1/queries/{query['query_id']}/classify", headers=org["headers"]).json()
    second = client.post(f"/api/v1/queries/{query['query_id']}/classify", headers=org["headers"]).json()

    assert second == []  # nothing new to add, same types already exist
    all_intents = client.get(f"/api/v1/queries/{query['query_id']}/intents", headers=org["headers"]).json()
    types = [i["intent_type"] for i in all_intents["items"]]
    assert len(types) == len(set(types))  # no duplicate types
    assert len(all_intents["items"]) == len(first)


def test_archived_query_status_not_reverted_by_classify(client: TestClient, register_org) -> None:
    org = register_org()
    query = _import_one(client, org["headers"], "چیزی که هیچ قانونی برایش نداریم")
    client.post(f"/api/v1/queries/{query['query_id']}/archive", headers=org["headers"])

    client.post(
        f"/api/v1/queries/{query['query_id']}/intents",
        json={"intent_type": "information", "is_primary": True},
        headers=org["headers"],
    )
    refreshed = client.get(f"/api/v1/queries/{query['query_id']}", headers=org["headers"]).json()
    assert refreshed["status"] == "archived"


def test_manual_intent_override_creates_new_row_and_demotes_previous_primary(
    client: TestClient, register_org
) -> None:
    org = register_org()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")
    client.post(f"/api/v1/queries/{query['query_id']}/classify", headers=org["headers"])

    response = client.post(
        f"/api/v1/queries/{query['query_id']}/intents",
        json={"intent_type": "wholesale", "is_primary": True, "reason": "human override"},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["classification_source"] == "manual"
    assert response.json()["is_primary"] is True

    all_intents = client.get(f"/api/v1/queries/{query['query_id']}/intents", headers=org["headers"]).json()["items"]
    primaries = [i for i in all_intents if i["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["intent_type"] == "wholesale"


def test_bulk_classify_pending_queries(client: TestClient, register_org) -> None:
    org = register_org()
    _import_one(client, org["headers"], "قیمت ترنجبین")
    _import_one(client, org["headers"], "خرید عمده ترنجبین")

    response = client.post("/api/v1/queries/classify", headers=org["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scanned"] == 2
    assert body["classified"] == 2
