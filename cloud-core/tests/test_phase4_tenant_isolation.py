"""
THE GOLDEN TEST SUITE — Phase 4 edition (Evidence, ClaimEvidence).

Continues the pattern from test_tenant_isolation.py (Phase 1),
test_knowledge_tenant_isolation.py (Phase 2), and
test_phase3_tenant_isolation.py (Phase 3): Organization A must never
read, list, or write anything belonging to Organization B — including
every hop of Evidence's provenance chain (source/document/chunk) and
both sides of a ClaimEvidence link (claim/evidence).
"""

from fastapi.testclient import TestClient


def _create_source(client: TestClient, headers: dict, title: str = "Source") -> dict:
    return client.post(
        "/api/v1/sources", json={"source_type": "website", "title": title}, headers=headers
    ).json()


def _create_evidence(client: TestClient, headers: dict, source_id: str) -> dict:
    return client.post(
        "/api/v1/evidence",
        json={"source_id": source_id, "summary": "A finding."},
        headers=headers,
    ).json()


def _create_claim(client: TestClient, headers: dict) -> dict:
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"}, headers=headers
    ).json()
    subject = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=headers,
    ).json()
    return client.post(
        "/api/v1/claims",
        json={
            "knowledge_object_id": ko["id"],
            "subject_entity_id": subject["id"],
            "predicate": "has_taste",
            "object_value": "sweet",
        },
        headers=headers,
    ).json()


# --- Evidence ------------------------------------------------------------


def test_user_cannot_read_another_orgs_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])

    response = client.get(f"/api/v1/evidence/{evidence_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_attach_evidence_to_another_orgs_source(client: TestClient, register_org) -> None:
    """The Phase 3 two-hop principle, carried forward: fully
    authenticated within org A, but source_id points at org B."""
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])

    response = client.post(
        "/api/v1/evidence",
        json={"source_id": source_b["id"], "summary": "Smuggled evidence."},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_attach_evidence_to_another_orgs_document(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_a = _create_source(client, org_a["headers"])
    source_b = _create_source(client, org_b["headers"])
    document_b = client.post(
        f"/api/v1/documents?source_id={source_b['id']}",
        json={"title": "Doc B", "content": "x"},
        headers=org_b["headers"],
    ).json()

    response = client.post(
        "/api/v1/evidence",
        json={"source_id": source_a["id"], "document_id": document_b["id"], "summary": "x"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_evidence_list_never_includes_other_orgs_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_a = _create_source(client, org_a["headers"])
    source_b = _create_source(client, org_b["headers"])
    _create_evidence(client, org_a["headers"], source_a["id"])
    _create_evidence(client, org_b["headers"], source_b["id"])

    response = client.get("/api/v1/evidence", headers=org_a["headers"])
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["organization_id"] == org_a["organization"]["id"]


def test_user_cannot_update_another_orgs_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])

    response = client.patch(
        f"/api/v1/evidence/{evidence_b['id']}", json={"summary": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_review_another_orgs_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])

    response = client.post(
        f"/api/v1/evidence/{evidence_b['id']}/review", json={"status": "verified"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


# --- ClaimEvidence (both sides of the link) ------------------------------


def test_user_cannot_link_own_claim_to_another_orgs_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    claim_a = _create_claim(client, org_a["headers"])
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])

    response = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_a["id"], "evidence_id": evidence_b["id"]},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_link_own_evidence_to_another_orgs_claim(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_a = _create_source(client, org_a["headers"])
    evidence_a = _create_evidence(client, org_a["headers"], source_a["id"])
    claim_b = _create_claim(client, org_b["headers"])

    response = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_b["id"], "evidence_id": evidence_a["id"]},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_claim_evidence_link(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    claim_b = _create_claim(client, org_b["headers"])
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])
    link_b = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_b["id"], "evidence_id": evidence_b["id"]},
        headers=org_b["headers"],
    ).json()

    response = client.get(f"/api/v1/claim-evidence/{link_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_unlink_another_orgs_claim_evidence_link(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    claim_b = _create_claim(client, org_b["headers"])
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])
    link_b = client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_b["id"], "evidence_id": evidence_b["id"]},
        headers=org_b["headers"],
    ).json()

    response = client.delete(f"/api/v1/claim-evidence/{link_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_claim_evidence_list_never_includes_other_orgs_links(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()

    claim_a = _create_claim(client, org_a["headers"])
    source_a = _create_source(client, org_a["headers"])
    evidence_a = _create_evidence(client, org_a["headers"], source_a["id"])
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_a["id"], "evidence_id": evidence_a["id"]},
        headers=org_a["headers"],
    )

    claim_b = _create_claim(client, org_b["headers"])
    source_b = _create_source(client, org_b["headers"])
    evidence_b = _create_evidence(client, org_b["headers"], source_b["id"])
    client.post(
        "/api/v1/claim-evidence",
        json={"claim_id": claim_b["id"], "evidence_id": evidence_b["id"]},
        headers=org_b["headers"],
    )

    response = client.get("/api/v1/claim-evidence", headers=org_a["headers"])
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["claim_id"] == claim_a["id"]
