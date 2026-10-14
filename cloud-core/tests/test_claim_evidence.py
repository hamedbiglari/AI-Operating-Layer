"""
Integration tests for ClaimEvidence: linking/unlinking, and the
"Conflict foundations" aggregate recompute in
app/services/claim_evidence_service.py::recompute_claim_aggregate.
"""

from fastapi.testclient import TestClient


def _setup_claim(client: TestClient, headers: dict) -> dict:
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
    claim = client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko["id"],
            "subject_entity_id": subject["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=headers,
    ).json()
    return claim


def _create_evidence(client: TestClient, headers: dict, strength: str = "very_low", summary: str = "A finding.") -> dict:
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "Source"}, headers=headers
    ).json()
    return client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "evidence_strength": strength, "summary": summary},
        headers=headers,
    ).json()


def _verify_evidence(client: TestClient, headers: dict, evidence_id: str) -> dict:
    return client.post(
        f"/api/v1/evidence/{evidence_id}/review",
        json={"status": "verified"},
        headers=headers,
    ).json()


def _get_claim(client: TestClient, headers: dict, claim_id: str) -> dict:
    return client.get(f"/api/v1/claims/{claim_id}", headers=headers).json()


def test_link_unverified_evidence_does_not_move_the_aggregate(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    evidence = _create_evidence(client, org["headers"], strength="high")

    response = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "unverified"


def test_single_verified_high_strength_support_yields_moderate(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    evidence = _create_evidence(client, org["headers"], strength="high")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], evidence["id"])

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "moderate"


def test_two_verified_high_strength_supports_yield_strong(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    for _ in range(2):
        evidence = _create_evidence(client, org["headers"], strength="high")
        client.post(
            "/api/v1/claim-evidence",
            json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"},
            headers=org["headers"],
        )
        _verify_evidence(client, org["headers"], evidence["id"])

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "strong"


def test_strong_support_plus_strong_contradiction_yields_conflicting(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])

    support = _create_evidence(client, org["headers"], strength="high", summary="Supports it.")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": support["id"], "relation": "supports"},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], support["id"])

    contradiction = _create_evidence(client, org["headers"], strength="high", summary="Contradicts it.")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": contradiction["id"], "relation": "contradicts"},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], contradiction["id"])

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "conflicting"


def test_approved_claim_auto_downgrades_to_disputed_on_new_conflict(client: TestClient, register_org) -> None:
    """The safety guardrail: an APPROVED claim must not stay APPROVED
    once verified evidence contradicts it just as strongly as the
    evidence that (presumably) got it approved in the first place."""
    org = register_org()
    claim = _setup_claim(client, org["headers"])

    support = _create_evidence(client, org["headers"], strength="high")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": support["id"], "relation": "supports"},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], support["id"])

    approve = client.post(
        f"/api/v1/claims/{claim['id']}/review",
        json={"status": "approved", "note": "Looks solid."},
        headers=org["headers"],
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    contradiction = _create_evidence(client, org["headers"], strength="high")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": contradiction["id"], "relation": "contradicts"},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], contradiction["id"])

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["status"] == "disputed"
    assert refreshed["evidence_strength"] == "conflicting"


def test_duplicate_link_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    evidence = _create_evidence(client, org["headers"])
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"]},
        headers=org["headers"],
    )

    response = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"]},
        headers=org["headers"],
    )
    assert response.status_code == 409


def test_explicit_weight_overrides_strength_based_weight(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    # VERY_LOW would normally weigh 0.25; override to 1.0 so a single
    # link alone crosses the MODERATE net threshold.
    evidence = _create_evidence(client, org["headers"], strength="very_low")
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports", "weight": 1.0},
        headers=org["headers"],
    )
    _verify_evidence(client, org["headers"], evidence["id"])

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "moderate"


def test_unlink_resolves_conflict(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])

    support = _create_evidence(client, org["headers"], strength="high")
    link_support = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": support["id"], "relation": "supports"},
        headers=org["headers"],
    ).json()
    _verify_evidence(client, org["headers"], support["id"])

    contradiction = _create_evidence(client, org["headers"], strength="high")
    link_contradiction = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": contradiction["id"], "relation": "contradicts"},
        headers=org["headers"],
    ).json()
    _verify_evidence(client, org["headers"], contradiction["id"])

    assert _get_claim(client, org["headers"], claim["id"])["evidence_strength"] == "conflicting"

    delete_response = client.delete(f"/api/v1/claim-evidence/{link_contradiction['id']}", headers=org["headers"])
    assert delete_response.status_code == 204

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "moderate"
    _ = link_support  # kept for clarity of what remains linked


def test_update_link_relation_triggers_recompute(client: TestClient, register_org) -> None:
    org = register_org()
    claim = _setup_claim(client, org["headers"])
    evidence = _create_evidence(client, org["headers"], strength="high")
    link = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"},
        headers=org["headers"],
    ).json()
    _verify_evidence(client, org["headers"], evidence["id"])
    assert _get_claim(client, org["headers"], claim["id"])["evidence_strength"] == "moderate"

    response = client.patch(
        f"/api/v1/claim-evidence/{link['id']}",
        json={"relation": "contradicts"},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text

    refreshed = _get_claim(client, org["headers"], claim["id"])
    assert refreshed["evidence_strength"] == "insufficient"
