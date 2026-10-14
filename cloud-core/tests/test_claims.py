"""
Integration tests for Claims: creation, the object_entity_id/object_value
validation rule, and the review lifecycle.
"""

from fastapi.testclient import TestClient


def _setup_ko_with_entities(client: TestClient, headers: dict) -> dict:
    ko = client.post(
        "/api/v1/knowledge",
        json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=headers,
    ).json()
    subject = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=headers,
    ).json()
    obj = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "compound", "canonical_name": "Mannitol"},
        headers=headers,
    ).json()
    return {"ko": ko, "subject": subject, "object": obj}


def test_create_claim_with_object_entity(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
            "confidence": 0.9,
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["predicate"] == "contains"
    assert body["status"] == "draft"
    assert body["evidence_strength"] == "unverified"
    assert body["human_reviewed"] is False


def test_create_claim_with_object_value_literal(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201
    assert response.json()["object_value"] == "sweet"


def test_claim_without_object_entity_or_value_is_rejected(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_claim_object_entity_from_another_knowledge_object_in_same_org_is_allowed(
    client: TestClient, register_org
) -> None:
    """Entities live under a Knowledge Object, but a Claim can reference
    any entity within the SAME organization regardless of which
    Knowledge Object it was created under (cross-referencing, e.g.
    "Taranjabin contains Mannitol" where Mannitol has its own KO)."""
    org = register_org()
    ko1 = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=org["headers"],
    ).json()
    ko2 = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Mannitol", "object_type": "compound"},
        headers=org["headers"],
    ).json()
    subject = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko1["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=org["headers"],
    ).json()
    obj = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko2["id"], "entity_type": "compound", "canonical_name": "Mannitol"},
        headers=org["headers"],
    ).json()

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko1["id"],
            "subject_entity_id": subject["id"],
            "predicate": "contains",
            "object_entity_id": obj["id"],
        },
        headers=org["headers"],
    )
    assert response.status_code == 201


def test_review_claim_marks_human_reviewed_and_sets_status(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()
    assert claim["human_reviewed"] is False

    response = client.post(
        f"/api/v1/claims/{claim['id']}/review",
        json={"status": "approved", "evidence_strength": "moderate", "note": "Looks solid"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["human_reviewed"] is True
    assert body["evidence_strength"] == "moderate"


def test_review_with_non_review_status_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.post(
        f"/api/v1/claims/{claim['id']}/review",
        json={"status": "draft"},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_plain_update_cannot_change_status(client: TestClient, register_org) -> None:
    """Regression guard for the schema-level design decision: ClaimUpdate
    has no `status` field at all, so it's structurally impossible for a
    plain PATCH to bypass the review action."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"status": "approved", "predicate": "contains_updated"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["predicate"] == "contains_updated"


def test_list_claims_filtered_by_status(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()
    client.post(
        f"/api/v1/claims/{claim['id']}/review",
        json={"status": "approved"},
        headers=org["headers"],
    )

    approved = client.get("/api/v1/claims?status=approved", headers=org["headers"]).json()
    assert any(c["id"] == claim["id"] for c in approved["items"])

    draft = client.get("/api/v1/claims?status=draft", headers=org["headers"]).json()
    assert all(c["id"] != claim["id"] for c in draft["items"])


# --- Regression tests for the Phase 2 review's three MUST FIX findings -----


def test_create_claim_with_both_object_entity_and_value_is_rejected(
    client: TestClient, register_org
) -> None:
    """MUST FIX #1: the original CHECK constraint and Pydantic validator
    only required "at least one" of object_entity_id/object_value,
    which wrongly allowed BOTH to be set simultaneously. This must now
    be a true XOR, rejected at the API layer with a clean 422 (not a
    raw 500 from the database CHECK constraint)."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])

    response = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
            "object_value": "also this",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_patch_can_switch_from_value_to_entity_in_one_call(
    client: TestClient, register_org
) -> None:
    """MUST FIX #2: switching representations must clear the other side
    automatically, without the client needing to explicitly null it out."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=org["headers"],
    ).json()
    assert claim["object_value"] == "sweet"
    assert claim["object_entity_id"] is None

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"object_entity_id": ctx["object"]["id"]},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object_entity_id"] == ctx["object"]["id"]
    assert body["object_value"] is None  # automatically cleared


def test_patch_can_switch_from_entity_to_value_in_one_call(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"object_value": "a literal now"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object_value"] == "a literal now"
    assert body["object_entity_id"] is None


def test_patch_sending_both_object_fields_non_null_is_rejected(
    client: TestClient, register_org
) -> None:
    """MUST FIX #2: sending both as non-null in the same PATCH must be
    rejected outright, not silently resolved in favor of one side."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_value": "sweet",
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"object_entity_id": ctx["object"]["id"], "object_value": "still sweet"},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_patch_clearing_object_entity_without_replacement_is_rejected(
    client: TestClient, register_org
) -> None:
    """MUST FIX #2: explicitly nulling object_entity_id with no
    object_value provided (and none already set) must be rejected —
    it would otherwise leave the claim with neither representation."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"object_entity_id": None},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_patch_clearing_object_value_without_replacement_is_rejected(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"object_value": None},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_patch_omitting_object_fields_leaves_them_unchanged(
    client: TestClient, register_org
) -> None:
    """MUST FIX #2 (the positive case): a PATCH that never mentions
    object_entity_id/object_value at all must leave whichever
    representation was already set completely untouched."""
    org = register_org()
    ctx = _setup_ko_with_entities(client, org["headers"])
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ctx["ko"]["id"],
            "subject_entity_id": ctx["subject"]["id"],
            "predicate": "contains",
            "object_entity_id": ctx["object"]["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/claims/{claim['id']}",
        json={"predicate": "definitely_contains"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["predicate"] == "definitely_contains"
    assert body["object_entity_id"] == ctx["object"]["id"]
    assert body["object_value"] is None
