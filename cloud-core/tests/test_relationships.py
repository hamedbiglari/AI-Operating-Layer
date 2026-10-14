"""
Integration tests for Relationships (graph edges), including the
polymorphic subject/object node resolution.
"""

from fastapi.testclient import TestClient


def _setup_two_entities(client: TestClient, headers: dict) -> dict:
    ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=headers,
    ).json()
    e1 = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=headers,
    ).json()
    e2 = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "compound", "canonical_name": "Mannitol"},
        headers=headers,
    ).json()
    return {"ko": ko, "e1": e1, "e2": e2}


def test_create_entity_to_entity_relationship(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])

    response = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity",
            "subject_id": ctx["e1"]["id"],
            "predicate": "contains",
            "object_type": "entity",
            "object_id": ctx["e2"]["id"],
            "confidence": 0.85,
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["subject_type"] == "entity"


def test_create_entity_to_knowledge_object_relationship(client: TestClient, register_org) -> None:
    """Exercises the polymorphic node resolver with mixed node types."""
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])
    other_ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Related Topic", "object_type": "topic"},
        headers=org["headers"],
    ).json()

    response = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity",
            "subject_id": ctx["e1"]["id"],
            "predicate": "related_to",
            "object_type": "knowledge_object",
            "object_id": other_ko["id"],
        },
        headers=org["headers"],
    )
    assert response.status_code == 201


def test_relationship_to_unknown_entity_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])

    response = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity",
            "subject_id": ctx["e1"]["id"],
            "predicate": "contains",
            "object_type": "entity",
            "object_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_list_relationships_filtered_by_subject(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": ctx["e1"]["id"], "predicate": "contains",
            "object_type": "entity", "object_id": ctx["e2"]["id"],
        },
        headers=org["headers"],
    )

    response = client.get(
        f"/api/v1/relationships?subject_id={ctx['e1']['id']}", headers=org["headers"]
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_knowledge_object_relations_endpoint_returns_edges_from_either_side(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": ctx["e1"]["id"], "predicate": "part_of",
            "object_type": "knowledge_object", "object_id": ctx["ko"]["id"],
        },
        headers=org["headers"],
    )

    response = client.get(
        f"/api/v1/knowledge/{ctx['ko']['id']}/relations", headers=org["headers"]
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_update_relationship_status(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])
    edge = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": ctx["e1"]["id"], "predicate": "contains",
            "object_type": "entity", "object_id": ctx["e2"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/relationships/{edge['id']}",
        json={"status": "disputed"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disputed"


def test_viewer_cannot_create_relationship(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_two_entities(client, org["headers"])
    client.post(
        "/api/v1/users",
        json={
            "email": "rel-viewer@example.dev", "name": "Viewer",
            "password": "supersecret123", "role": "viewer",
        },
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "rel-viewer@example.dev", "password": "supersecret123"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": ctx["e1"]["id"], "predicate": "contains",
            "object_type": "entity", "object_id": ctx["e2"]["id"],
        },
        headers=viewer_headers,
    )
    assert response.status_code == 403


# --- Regression tests for the Phase 2 review's MUST FIX #3 -----------------


def test_relations_endpoint_total_counts_self_loop_edge_exactly_once(
    client: TestClient, register_org
) -> None:
    """MUST FIX #3: the previous implementation computed
    `total = subject_total + object_total` from two separate queries,
    which double-counts an edge where the same Knowledge Object is both
    the subject AND the object. A single OR query must count it once."""
    org = register_org()
    ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Self-Referential Topic", "object_type": "topic"},
        headers=org["headers"],
    ).json()
    other_ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Other Topic", "object_type": "topic"},
        headers=org["headers"],
    ).json()
    entity = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "topic", "canonical_name": "E"},
        headers=org["headers"],
    ).json()

    # A self-loop: `ko` is both endpoints of this edge, resolved via the
    # entity as subject and `ko` itself as object, then a second edge
    # with `ko` explicitly as subject and `other_ko` as object.
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "knowledge_object", "subject_id": ko["id"], "predicate": "self_referential",
            "object_type": "knowledge_object", "object_id": ko["id"],
        },
        headers=org["headers"],
    )
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "knowledge_object", "subject_id": ko["id"], "predicate": "related_to",
            "object_type": "knowledge_object", "object_id": other_ko["id"],
        },
        headers=org["headers"],
    )
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": entity["id"], "predicate": "part_of",
            "object_type": "knowledge_object", "object_id": ko["id"],
        },
        headers=org["headers"],
    )

    response = client.get(f"/api/v1/knowledge/{ko['id']}/relations", headers=org["headers"])
    assert response.status_code == 200
    body = response.json()
    # Exactly 3 distinct edges touch `ko`: the self-loop (once, not
    # twice), the edge to other_ko, and the edge from entity.
    assert body["total"] == 3
    assert len(body["items"]) == 3
    ids = [item["id"] for item in body["items"]]
    assert len(ids) == len(set(ids))  # no duplicates


def test_relations_endpoint_pagination_applies_to_combined_set(
    client: TestClient, register_org
) -> None:
    """MUST FIX #3: limit/offset must apply to the true combined
    (subject-side + object-side) result set, not to each side
    independently before merging. With 5 total edges and limit=2, we
    must get exactly 2 items per page and be able to page through all 5
    without gaps or repeats."""
    org = register_org()
    ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Hub", "object_type": "topic"},
        headers=org["headers"],
    ).json()
    entities = [
        client.post(
            "/api/v1/entities",
            json={"knowledge_object_id": ko["id"], "entity_type": "topic", "canonical_name": f"E{i}"},
            headers=org["headers"],
        ).json()
        for i in range(5)
    ]
    # 5 edges, each connecting a distinct entity to the hub KO — all
    # touch `ko` from the "object" side.
    for entity in entities:
        client.post(
            "/api/v1/relationships",
            json={
                "subject_type": "entity", "subject_id": entity["id"], "predicate": "part_of",
                "object_type": "knowledge_object", "object_id": ko["id"],
            },
            headers=org["headers"],
        )

    seen_ids: set[str] = set()
    for offset in (0, 2, 4):
        page = client.get(
            f"/api/v1/knowledge/{ko['id']}/relations?limit=2&offset={offset}",
            headers=org["headers"],
        ).json()
        assert page["total"] == 5
        seen_ids.update(item["id"] for item in page["items"])

    assert len(seen_ids) == 5  # every edge was reachable exactly once across pages
