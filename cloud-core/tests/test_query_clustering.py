"""
Integration tests for /queries/cluster and /query-clusters — the word
n-gram Jaccard clustering algorithm (see query_cluster_service.py's
module docstring for why this, not embeddings, was chosen for v1).
"""

import json

from fastapi.testclient import TestClient


def _import(client: TestClient, headers: dict, texts: list[str]) -> None:
    client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": json.dumps([{"query": t} for t in texts])},
        headers=headers,
    )


def test_similar_queries_cluster_together(client: TestClient, register_org) -> None:
    org = register_org()
    _import(
        client, org["headers"],
        [
            "قیمت ترنجبین اصل",
            "قیمت ترنجبین اصل تهران",
            "طرز تهیه آش رشته با گوجه",
        ],
    )

    response = client.post("/api/v1/queries/cluster", headers=org["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["clustered_query_count"] == 3
    # at least 2 clusters expected: the two "قیمت ترنجبین ..." queries
    # share enough shingles to merge, the unrelated third query should
    # not join them.
    assert body["cluster_count"] >= 2

    clusters = client.get("/api/v1/query-clusters", headers=org["headers"]).json()
    assert clusters["total"] == body["cluster_count"]

    # find the cluster containing more than one member
    multi_member_cluster = None
    for cluster in clusters["items"]:
        members = client.get(f"/api/v1/query-clusters/{cluster['id']}/members", headers=org["headers"]).json()
        if members["total"] > 1:
            multi_member_cluster = members
            break
    assert multi_member_cluster is not None
    assert multi_member_cluster["total"] == 2


def test_reclustering_replaces_previous_clusters(client: TestClient, register_org) -> None:
    org = register_org()
    _import(client, org["headers"], ["قیمت ترنجبین اصل", "قیمت ترنجبین درجه یک"])
    client.post("/api/v1/queries/cluster", headers=org["headers"])
    first = client.get("/api/v1/query-clusters", headers=org["headers"]).json()

    # cluster again with no new data - should be idempotent, not additive
    client.post("/api/v1/queries/cluster", headers=org["headers"])
    second = client.get("/api/v1/query-clusters", headers=org["headers"]).json()
    assert second["total"] == first["total"]


def test_archived_queries_excluded_from_clustering(client: TestClient, register_org) -> None:
    org = register_org()
    _import(client, org["headers"], ["قیمت ترنجبین اصل"])
    listing = client.get("/api/v1/queries", headers=org["headers"]).json()
    query_id = listing["items"][0]["id"]
    client.post(f"/api/v1/queries/{query_id}/archive", headers=org["headers"])

    response = client.post("/api/v1/queries/cluster", headers=org["headers"])
    body = response.json()
    assert body["clustered_query_count"] == 0
