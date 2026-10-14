"""
THE GOLDEN TEST SUITE — Knowledge Core edition.

Extends the tenant-isolation guarantees proven in
tests/test_tenant_isolation.py (Phase 1: organizations/users/sites) to
every Phase 2 resource: Knowledge Objects, Entities, Claims,
Relationships, Knowledge Versions, and Knowledge Gaps.

The invariant under test, everywhere: Organization A must never be able
to read, list, or write anything belonging to Organization B's
Knowledge Object graph — not even by ID, not even a 403 that would
confirm the resource exists.
"""

from fastapi.testclient import TestClient


def _create_ko(client: TestClient, headers: dict, name: str = "Taranjabin") -> dict:
    return client.post(
        "/api/v1/knowledge",
        json={"canonical_name": name, "object_type": "plant"},
        headers=headers,
    ).json()


def _create_entity(client: TestClient, headers: dict, ko_id: str, name: str = "Entity") -> dict:
    return client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko_id, "entity_type": "plant", "canonical_name": name},
        headers=headers,
    ).json()


# --- Knowledge Objects ------------------------------------------------


def test_user_cannot_read_another_orgs_knowledge_object(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.get(f"/api/v1/knowledge/{ko_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_knowledge_object(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.patch(
        f"/api/v1/knowledge/{ko_b['id']}", json={"canonical_name": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_publish_another_orgs_knowledge_object(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.post(f"/api/v1/knowledge/{ko_b['id']}/publish", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_archive_another_orgs_knowledge_object(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.delete(f"/api/v1/knowledge/{ko_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_knowledge_object_list_never_includes_other_orgs_objects(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    _create_ko(client, org_a["headers"], "A Only")
    _create_ko(client, org_b["headers"], "B Only")

    response = client.get("/api/v1/knowledge", headers=org_a["headers"])
    names = [item["canonical_name"] for item in response.json()["items"]]
    assert "A Only" in names
    assert "B Only" not in names


def test_search_never_returns_other_orgs_objects(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _create_ko(client, org_a["headers"], "UniqueMarkerAlpha")
    _create_ko(client, org_b["headers"], "UniqueMarkerAlpha")

    response = client.get(
        "/api/v1/knowledge/search?q=UniqueMarkerAlpha", headers=org_a["headers"]
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["organization_id"] == org_a["organization"]["id"]


def test_knowledge_versions_never_leak_across_orgs(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.get(f"/api/v1/knowledge/{ko_b['id']}/versions", headers=org_a["headers"])
    assert response.status_code == 404


# --- Entities -----------------------------------------------------------


def test_user_cannot_read_another_orgs_entity(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])

    response = client.get(f"/api/v1/entities/{entity_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_entity(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])

    response = client.patch(
        f"/api/v1/entities/{entity_b['id']}", json={"canonical_name": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_attach_entity_to_another_orgs_knowledge_object(
    client: TestClient, register_org
) -> None:
    """The critical cross-object check: even though the caller is
    authenticated and the endpoint is otherwise well-formed, pointing
    knowledge_object_id at another org's KO must 404, not succeed."""
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.post(
        "/api/v1/entities",
        json={
            "knowledge_object_id": ko_b["id"],
            "entity_type": "plant",
            "canonical_name": "Smuggled Entity",
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_entity_list_never_includes_other_orgs_entities(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_a = _create_ko(client, org_a["headers"])
    ko_b = _create_ko(client, org_b["headers"])
    _create_entity(client, org_a["headers"], ko_a["id"], "A Entity")
    _create_entity(client, org_b["headers"], ko_b["id"], "B Entity")

    response = client.get("/api/v1/entities", headers=org_a["headers"])
    names = [item["canonical_name"] for item in response.json()["items"]]
    assert "A Entity" in names
    assert "B Entity" not in names


def test_nested_entities_route_404s_for_foreign_knowledge_object(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.get(f"/api/v1/knowledge/{ko_b['id']}/entities", headers=org_a["headers"])
    assert response.status_code == 404


# --- Claims ---------------------------------------------------------------


def test_user_cannot_create_claim_against_another_orgs_knowledge_object(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko_b["id"],
            "subject_entity_id": entity_b["id"],
            "predicate": "contains",
            "object_value": "smuggled",
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_create_claim_referencing_another_orgs_entity(
    client: TestClient, register_org
) -> None:
    """Own Knowledge Object, but the subject entity belongs to another
    org — must still 404, proving the entity ownership check is
    independent of the knowledge_object ownership check."""
    org_a = register_org()
    org_b = register_org()
    ko_a = _create_ko(client, org_a["headers"])
    ko_b = _create_ko(client, org_b["headers"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko_a["id"],
            "subject_entity_id": entity_b["id"],
            "predicate": "contains",
            "object_value": "smuggled",
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_or_review_another_orgs_claim(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])
    claim_b = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko_b["id"],
            "subject_entity_id": entity_b["id"],
            "predicate": "contains",
            "object_value": "x",
        },
        headers=org_b["headers"],
    ).json()

    get_response = client.get(f"/api/v1/claims/{claim_b['id']}", headers=org_a["headers"])
    assert get_response.status_code == 404

    review_response = client.post(
        f"/api/v1/claims/{claim_b['id']}/review",
        json={"status": "approved"},
        headers=org_a["headers"],
    )
    assert review_response.status_code == 404


def test_claims_list_never_includes_other_orgs_claims(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_a = _create_ko(client, org_a["headers"])
    ko_b = _create_ko(client, org_b["headers"])
    entity_a = _create_entity(client, org_a["headers"], ko_a["id"])
    entity_b = _create_entity(client, org_b["headers"], ko_b["id"])
    claim_a = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko_a["id"], "subject_entity_id": entity_a["id"],
            "predicate": "contains", "object_value": "a",
        },
        headers=org_a["headers"],
    ).json()
    client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko_b["id"], "subject_entity_id": entity_b["id"],
            "predicate": "contains", "object_value": "b",
        },
        headers=org_b["headers"],
    )

    response = client.get("/api/v1/claims", headers=org_a["headers"])
    ids = [item["id"] for item in response.json()["items"]]
    assert claim_a["id"] in ids
    assert len(ids) == 1


# --- Relationships --------------------------------------------------------


def test_user_cannot_create_relationship_over_another_orgs_entities(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    e1_b = _create_entity(client, org_b["headers"], ko_b["id"], "E1")
    e2_b = _create_entity(client, org_b["headers"], ko_b["id"], "E2")

    response = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": e1_b["id"], "predicate": "contains",
            "object_type": "entity", "object_id": e2_b["id"],
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_relationship(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    e1_b = _create_entity(client, org_b["headers"], ko_b["id"], "E1")
    e2_b = _create_entity(client, org_b["headers"], ko_b["id"], "E2")
    edge_b = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": e1_b["id"], "predicate": "contains",
            "object_type": "entity", "object_id": e2_b["id"],
        },
        headers=org_b["headers"],
    ).json()

    response = client.get(f"/api/v1/relationships/{edge_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_relationships_list_never_includes_other_orgs_edges(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_a = _create_ko(client, org_a["headers"])
    ko_b = _create_ko(client, org_b["headers"])
    e1_a = _create_entity(client, org_a["headers"], ko_a["id"], "A1")
    e2_a = _create_entity(client, org_a["headers"], ko_a["id"], "A2")
    e1_b = _create_entity(client, org_b["headers"], ko_b["id"], "B1")
    e2_b = _create_entity(client, org_b["headers"], ko_b["id"], "B2")
    edge_a = client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": e1_a["id"], "predicate": "contains",
            "object_type": "entity", "object_id": e2_a["id"],
        },
        headers=org_a["headers"],
    ).json()
    client.post(
        "/api/v1/relationships",
        json={
            "subject_type": "entity", "subject_id": e1_b["id"], "predicate": "contains",
            "object_type": "entity", "object_id": e2_b["id"],
        },
        headers=org_b["headers"],
    )

    response = client.get("/api/v1/relationships", headers=org_a["headers"])
    ids = [item["id"] for item in response.json()["items"]]
    assert edge_a["id"] in ids
    assert len(ids) == 1


# --- Knowledge Gaps ---------------------------------------------------------


def test_user_cannot_create_gap_against_another_orgs_knowledge_object(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])

    response = client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko_b["id"], "gap_type": "content_gap", "description": "smuggled"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_or_update_another_orgs_gap(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = _create_ko(client, org_b["headers"])
    gap_b = client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko_b["id"], "gap_type": "content_gap", "description": "x"},
        headers=org_b["headers"],
    ).json()

    get_response = client.get(f"/api/v1/knowledge-gaps/{gap_b['id']}", headers=org_a["headers"])
    assert get_response.status_code == 404

    update_response = client.patch(
        f"/api/v1/knowledge-gaps/{gap_b['id']}", json={"status": "resolved"}, headers=org_a["headers"]
    )
    assert update_response.status_code == 404


def test_gaps_list_never_includes_other_orgs_gaps(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_a = _create_ko(client, org_a["headers"])
    ko_b = _create_ko(client, org_b["headers"])
    gap_a = client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko_a["id"], "gap_type": "content_gap", "description": "a"},
        headers=org_a["headers"],
    ).json()
    client.post(
        "/api/v1/knowledge-gaps",
        json={"knowledge_object_id": ko_b["id"], "gap_type": "content_gap", "description": "b"},
        headers=org_b["headers"],
    )

    response = client.get("/api/v1/knowledge-gaps", headers=org_a["headers"])
    ids = [item["id"] for item in response.json()["items"]]
    assert gap_a["id"] in ids
    assert len(ids) == 1
