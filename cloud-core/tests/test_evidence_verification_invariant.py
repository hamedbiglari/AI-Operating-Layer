"""
Adversarial tests for the TWO-LAYER VERIFICATION INVARIANT (ADR-032).

The bug these exist to prevent: `ProductEvidence.verification_status ==
VERIFIED` sitting on top of an `Evidence` row that is DRAFT or
REJECTED. A recommendation engine reading only the link's own flag
would treat a rejected study as verified support.

Two defences are tested separately, because neither alone is enough:

1. **Write-time** - you cannot verify a link whose Evidence isn't
   verified.
2. **Read-time** - if the Evidence is rejected AFTER the link was
   verified, the link stops counting immediately. A write-time check
   structurally cannot catch this, because the revocation happens
   later.
"""

from fastapi.testclient import TestClient

from app.contracts import commerce as contract


def _product(client: TestClient, headers: dict, slug: str = "p") -> dict:
    product = client.post(
        "/api/v1/products", json={"name": "P", "slug": slug}, headers=headers
    ).json()
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=headers)
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=headers)
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"price": 100, "currency": "EUR"}, headers=headers,
    )
    return product


def _evidence(client: TestClient, headers: dict) -> dict:
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"}, headers=headers
    ).json()
    return client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": "A study."}, headers=headers
    ).json()


def _link(client: TestClient, headers: dict, product_id: str, evidence_id: str, claim: str = "Grade = A") -> dict:
    return client.post(
        f"/api/v1/products/{product_id}/evidence",
        json={"evidence_id": evidence_id, "claim": claim}, headers=headers,
    ).json()


# --- Layer 1: write-time -----------------------------------------------------


def test_cannot_verify_link_while_evidence_is_draft(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])  # status: draft
    link = _link(client, org["headers"], product["id"], evidence["id"])

    response = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )
    assert response.status_code == 422
    assert "draft" in response.text.lower()


def test_cannot_verify_link_while_evidence_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "rejected"}, headers=org["headers"],
    )
    link = _link(client, org["headers"], product["id"], evidence["id"])

    response = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )
    assert response.status_code == 422


def test_can_verify_link_once_evidence_is_verified(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "verified"}, headers=org["headers"],
    )
    link = _link(client, org["headers"], product["id"], evidence["id"])

    response = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"


def test_cannot_verify_trust_record_on_unverified_evidence(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])  # draft
    record = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": evidence["id"],
        },
        headers=org["headers"],
    ).json()

    response = client.post(
        f"/api/v1/trust-records/{record['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )
    assert response.status_code == 422


# --- Layer 2: read-time (revocation after the fact) --------------------------


def test_rejecting_evidence_later_revokes_effective_verification(
    client: TestClient, register_org, db_session
) -> None:
    """THE case a write-time check cannot catch: the link was
    legitimately verified, and the Evidence was rejected afterwards."""
    org = register_org()
    org_id = org["organization"]["id"]
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "verified"}, headers=org["headers"],
    )
    link = _link(client, org["headers"], product["id"], evidence["id"])
    client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )

    import uuid as _uuid
    pid = _uuid.UUID(product["id"])
    before = contract.get_evidence_summaries(
        db_session, product_ids=[pid], organization_id=_uuid.UUID(org_id)
    )[pid]
    assert before.verified == 1

    # Now the underlying study is rejected.
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "rejected"}, headers=org["headers"],
    )

    after = contract.get_evidence_summaries(
        db_session, product_ids=[pid], organization_id=_uuid.UUID(org_id)
    )[pid]
    assert after.verified == 0
    assert after.rejected == 1


def test_revoked_evidence_downgrades_a_recommendation(client: TestClient, register_org) -> None:
    """End to end: the same revocation must change what the
    recommendation engine sees."""
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "verified"}, headers=org["headers"],
    )
    link = _link(client, org["headers"], product["id"], evidence["id"])
    client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )

    before = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "persist": False}, headers=org["headers"],
    ).json()["recommendations"][0]
    assert before["evidence_state"] in ("partial", "established")

    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "rejected"}, headers=org["headers"],
    )

    after = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "persist": False}, headers=org["headers"],
    ).json()["recommendations"][0]
    assert after["evidence_state"] == "negative"
    assert after["evidence_score"] < before["evidence_score"]


def test_revoked_trust_evidence_downgrades_trust_signal(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])
    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "verified"}, headers=org["headers"],
    )
    record = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": evidence["id"],
        },
        headers=org["headers"],
    ).json()
    client.post(
        f"/api/v1/trust-records/{record['id']}/verify",
        json={"verification_status": "verified"}, headers=org["headers"],
    )

    before = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "persist": False}, headers=org["headers"],
    ).json()["recommendations"][0]
    assert before["trust_state"] in ("partial", "established")

    client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "rejected"}, headers=org["headers"],
    )

    after = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "persist": False}, headers=org["headers"],
    ).json()["recommendations"][0]
    assert after["trust_state"] == "negative"


def test_link_verified_but_evidence_still_draft_counts_as_unverified(
    client: TestClient, register_org, db_session
) -> None:
    """Belt and braces: even if such a row existed (e.g. written before
    this invariant, or by a direct DB edit), the read contract must not
    count it as verified."""
    import uuid as _uuid
    from app.models.product_evidence import ProductEvidence
    from app.models.enums import VerificationStatus

    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"])  # stays draft
    link = _link(client, org["headers"], product["id"], evidence["id"])

    # Simulate the contradictory legacy state directly.
    row = db_session.get(ProductEvidence, _uuid.UUID(link["id"]))
    row.verification_status = VerificationStatus.VERIFIED
    db_session.flush()

    pid = _uuid.UUID(product["id"])
    summary = contract.get_evidence_summaries(
        db_session, product_ids=[pid], organization_id=_uuid.UUID(org["organization"]["id"])
    )[pid]
    assert summary.verified == 0
    assert summary.unverified == 1
