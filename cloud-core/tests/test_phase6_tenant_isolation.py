"""
THE GOLDEN TEST SUITE — Phase 6 edition (Query Engine).

Continues the pattern from every prior phase: Organization A must
never read, list, or write anything belonging to Organization B,
including both directions of the QueryGroup<->Query membership two-hop
(a group from another org; a query from another org).
"""

import json

from fastapi.testclient import TestClient


def _import_one(client: TestClient, headers: dict, text: str = "قیمت ترنجبین") -> dict:
    response = client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": json.dumps([{"query": text}])},
        headers=headers,
    )
    return response.json()["items"][0]


def _create_group(client: TestClient, headers: dict, name: str = "G") -> dict:
    return client.post(
        "/api/v1/query-groups", json={"name": name, "primary_intent": "price"}, headers=headers
    ).json()


# --- Queries -------------------------------------------------------------


def test_user_cannot_read_another_orgs_query(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    query_b = _import_one(client, org_b["headers"])

    response = client.get(f"/api/v1/queries/{query_b['query_id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_or_archive_another_orgs_query(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    query_b = _import_one(client, org_b["headers"])

    update_response = client.patch(
        f"/api/v1/queries/{query_b['query_id']}", json={"priority": "critical"}, headers=org_a["headers"]
    )
    assert update_response.status_code == 404

    archive_response = client.post(f"/api/v1/queries/{query_b['query_id']}/archive", headers=org_a["headers"])
    assert archive_response.status_code == 404


def test_query_list_never_includes_other_orgs_queries(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _import_one(client, org_a["headers"], "قیمت ترنجبین")
    _import_one(client, org_b["headers"], "خرید ترنجبین")

    response = client.get("/api/v1/queries", headers=org_a["headers"])
    assert response.json()["total"] == 1


def test_user_cannot_classify_another_orgs_query(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    query_b = _import_one(client, org_b["headers"])

    response = client.post(f"/api/v1/queries/{query_b['query_id']}/classify", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_create_manual_intent_on_another_orgs_query(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    query_b = _import_one(client, org_b["headers"])

    response = client.post(
        f"/api/v1/queries/{query_b['query_id']}/intents",
        json={"intent_type": "price", "is_primary": True},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_list_another_orgs_query_intents(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    query_b = _import_one(client, org_b["headers"])

    response = client.get(f"/api/v1/queries/{query_b['query_id']}/intents", headers=org_a["headers"])
    assert response.status_code == 404


# --- Query Groups (both directions of the two-hop) ------------------------


def test_user_cannot_read_another_orgs_query_group(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    group_b = _create_group(client, org_b["headers"])

    response = client.get(f"/api/v1/query-groups/{group_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_query_group(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    group_b = _create_group(client, org_b["headers"])

    response = client.patch(
        f"/api/v1/query-groups/{group_b['id']}", json={"name": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_add_member_to_another_orgs_group(client: TestClient, register_org) -> None:
    """Two-hop, direction 1: own query, another org's group."""
    org_a = register_org()
    org_b = register_org()
    group_b = _create_group(client, org_b["headers"])
    query_a = _import_one(client, org_a["headers"])

    response = client.post(
        f"/api/v1/query-groups/{group_b['id']}/members", json={"query_id": query_a["query_id"]}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_add_another_orgs_query_to_own_group(client: TestClient, register_org) -> None:
    """Two-hop, direction 2: own group, another org's query."""
    org_a = register_org()
    org_b = register_org()
    group_a = _create_group(client, org_a["headers"])
    query_b = _import_one(client, org_b["headers"])

    response = client.post(
        f"/api/v1/query-groups/{group_a['id']}/members", json={"query_id": query_b["query_id"]}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_query_group_list_never_includes_other_orgs_groups(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _create_group(client, org_a["headers"], "A Only")
    _create_group(client, org_b["headers"], "B Only")

    response = client.get("/api/v1/query-groups", headers=org_a["headers"])
    names = [g["name"] for g in response.json()["items"]]
    assert "A Only" in names
    assert "B Only" not in names


def test_user_cannot_read_another_orgs_knowledge_need_assessment(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    group_b = _create_group(client, org_b["headers"])

    response = client.get(
        f"/api/v1/query-groups/{group_b['id']}/knowledge-need-assessment", headers=org_a["headers"]
    )
    assert response.status_code == 404


# --- Query Clusters ---------------------------------------------------


def test_user_cannot_read_another_orgs_query_cluster(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _import_one(client, org_b["headers"])
    client.post("/api/v1/queries/cluster", headers=org_b["headers"])
    cluster_b = client.get("/api/v1/query-clusters", headers=org_b["headers"]).json()["items"][0]

    response = client.get(f"/api/v1/query-clusters/{cluster_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_list_another_orgs_query_cluster_members(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _import_one(client, org_b["headers"])
    client.post("/api/v1/queries/cluster", headers=org_b["headers"])
    cluster_b = client.get("/api/v1/query-clusters", headers=org_b["headers"]).json()["items"][0]

    response = client.get(f"/api/v1/query-clusters/{cluster_b['id']}/members", headers=org_a["headers"])
    assert response.status_code == 404


def test_cluster_run_never_clusters_another_orgs_queries(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _import_one(client, org_a["headers"], "قیمت ترنجبین")
    _import_one(client, org_b["headers"], "خرید ترنجبین عمده")

    response = client.post("/api/v1/queries/cluster", headers=org_a["headers"])
    assert response.json()["clustered_query_count"] == 1
