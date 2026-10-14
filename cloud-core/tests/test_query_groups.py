"""
Integration tests for /query-groups, including the Knowledge Need
assessment (a computed judgment, never a persisted gap — see
query_group_service.py's module docstring).
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


def _create_entity(client: TestClient, headers: dict) -> dict:
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"}, headers=headers
    ).json()
    return client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=headers,
    ).json()


def test_create_query_group_without_entity(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/query-groups",
        json={"name": "Authenticity questions", "primary_intent": "authenticity"},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["target_entity_id"] is None


def test_create_query_group_with_entity(client: TestClient, register_org) -> None:
    org = register_org()
    entity = _create_entity(client, org["headers"])
    response = client.post(
        "/api/v1/query-groups",
        json={"name": "Price questions", "primary_intent": "price", "target_entity_id": entity["id"]},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["target_entity_id"] == entity["id"]


def test_add_and_list_group_members(client: TestClient, register_org) -> None:
    org = register_org()
    group = client.post(
        "/api/v1/query-groups", json={"name": "G", "primary_intent": "price"}, headers=org["headers"]
    ).json()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")

    response = client.post(
        f"/api/v1/query-groups/{group['id']}/members", json={"query_id": query["query_id"]}, headers=org["headers"]
    )
    assert response.status_code == 201, response.text

    members = client.get(f"/api/v1/query-groups/{group['id']}/members", headers=org["headers"]).json()
    assert members["total"] == 1
    assert members["items"][0]["query_id"] == query["query_id"]


def test_duplicate_membership_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    group = client.post(
        "/api/v1/query-groups", json={"name": "G", "primary_intent": "price"}, headers=org["headers"]
    ).json()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")
    client.post(f"/api/v1/query-groups/{group['id']}/members", json={"query_id": query["query_id"]}, headers=org["headers"])

    response = client.post(
        f"/api/v1/query-groups/{group['id']}/members", json={"query_id": query["query_id"]}, headers=org["headers"]
    )
    assert response.status_code == 409


def test_remove_group_member(client: TestClient, register_org) -> None:
    org = register_org()
    group = client.post(
        "/api/v1/query-groups", json={"name": "G", "primary_intent": "price"}, headers=org["headers"]
    ).json()
    query = _import_one(client, org["headers"], "قیمت ترنجبین")
    membership = client.post(
        f"/api/v1/query-groups/{group['id']}/members", json={"query_id": query["query_id"]}, headers=org["headers"]
    ).json()

    response = client.delete(
        f"/api/v1/query-groups/{group['id']}/members/{membership['id']}", headers=org["headers"]
    )
    assert response.status_code == 204

    members = client.get(f"/api/v1/query-groups/{group['id']}/members", headers=org["headers"]).json()
    assert members["total"] == 0


def test_knowledge_need_assessment_without_entity(client: TestClient, register_org) -> None:
    org = register_org()
    group = client.post(
        "/api/v1/query-groups", json={"name": "G", "primary_intent": "price"}, headers=org["headers"]
    ).json()

    response = client.get(f"/api/v1/query-groups/{group['id']}/knowledge-need-assessment", headers=org["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_target_entity"] is False
    assert body["is_gap_worthy"] is False


def test_knowledge_need_assessment_gap_worthy_with_no_claims(client: TestClient, register_org) -> None:
    org = register_org()
    entity = _create_entity(client, org["headers"])
    group = client.post(
        "/api/v1/query-groups",
        json={"name": "G", "primary_intent": "price", "target_entity_id": entity["id"]},
        headers=org["headers"],
    ).json()

    response = client.get(f"/api/v1/query-groups/{group['id']}/knowledge-need-assessment", headers=org["headers"])
    body = response.json()
    assert body["has_target_entity"] is True
    assert body["claim_count"] == 0
    assert body["is_gap_worthy"] is True


def test_knowledge_need_assessment_not_gap_worthy_with_adequate_evidence(client: TestClient, register_org) -> None:
    org = register_org()
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"}, headers=org["headers"]
    ).json()
    entity = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=org["headers"],
    ).json()
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko["id"],
            "subject_entity_id": entity["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=org["headers"],
    ).json()
    # Manually push the claim's aggregate to MODERATE-or-above via the
    # real Phase 4 claim_evidence path.
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"}, headers=org["headers"]
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "evidence_strength": "high", "summary": "Supports it."},
        headers=org["headers"],
    ).json()
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"},
        headers=org["headers"],
    )
    client.post(f"/api/v1/evidence/{evidence['id']}/review", json={"status": "verified"}, headers=org["headers"])

    group = client.post(
        "/api/v1/query-groups",
        json={"name": "G", "primary_intent": "price", "target_entity_id": entity["id"]},
        headers=org["headers"],
    ).json()

    response = client.get(f"/api/v1/query-groups/{group['id']}/knowledge-need-assessment", headers=org["headers"])
    body = response.json()
    assert body["claim_count"] == 1
    assert body["adequately_evidenced_claim_count"] == 1
    assert body["is_gap_worthy"] is False
