"""
SAME-TENANT SEMANTIC SCOPE.

Cross-tenant tests catch the case where Org A borrows Org B's data.
They cannot catch the subtler one: **within a single organization**,
attaching Product B's lab report to Product A as evidence for a claim
about Product A.

Both rows are legitimately owned by the same tenant, so every tenant
check passes. Nothing in the schema says a piece of evidence is
"about" a particular product.

These tests pin down what the system actually does about that —
deliberately documenting a LIMIT rather than asserting a guarantee the
implementation does not provide. Recorded in KNOWN_ISSUES and ADR-033.

The honest position: the system does not and cannot semantically
validate that a study is about the product it is cited for. What it
does guarantee is that the pairing is explicit, attributable and
reviewable — never inferred. Claiming more would overstate what schema
design can do.
"""

from fastapi.testclient import TestClient


def _product(client: TestClient, headers: dict, slug: str, name: str) -> dict:
    return client.post("/api/v1/products", json={"name": name, "slug": slug}, headers=headers).json()


def _verified_evidence(client: TestClient, headers: dict, summary: str) -> dict:
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "Lab report"},
        headers=headers,
    ).json()
    evidence = client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": summary}, headers=headers
    ).json()
    return client.post(
        f"/api/v1/evidence/{evidence['id']}/review", json={"status": "verified"}, headers=headers
    ).json()


def test_evidence_about_one_product_can_be_attached_to_another_in_same_tenant(
    client: TestClient, register_org
) -> None:
    """DOCUMENTED LIMIT, not an endorsement.

    The system permits this pairing because it has no way to know what
    a free-text evidence summary is 'about'. What it does NOT do is
    treat the pairing as self-justifying: the link is created
    UNVERIFIED and a human must both write the claim and verify it,
    leaving an audit record of who did."""
    org = register_org()
    product_a = _product(client, org["headers"], "product-a", "Product A")
    _product(client, org["headers"], "product-b", "Product B")
    evidence_about_b = _verified_evidence(client, org["headers"], "Lab report for Product B, batch 42.")

    link = client.post(
        f"/api/v1/products/{product_a['id']}/evidence",
        json={"evidence_id": evidence_about_b["id"], "claim": "Product A is Grade A"},
        headers=org["headers"],
    )
    assert link.status_code == 201
    # The crucial part: it is NOT automatically verified.
    assert link.json()["verification_status"] == "unverified"


def test_such_a_link_contributes_nothing_until_a_human_verifies_it(
    client: TestClient, register_org
) -> None:
    """The mitigation that actually matters: an unverified link is
    worth exactly as much as no link at all to the recommendation
    engine."""
    org = register_org()
    product_a = _product(client, org["headers"], "product-a", "Product A")
    client.post(f"/api/v1/products/{product_a['id']}/status", json={"status": "in_review"}, headers=org["headers"])
    client.post(f"/api/v1/products/{product_a['id']}/status", json={"status": "published"}, headers=org["headers"])
    client.post(
        f"/api/v1/products/{product_a['id']}/offers",
        json={"price": 10, "currency": "EUR"}, headers=org["headers"],
    )
    evidence_about_b = _verified_evidence(client, org["headers"], "Lab report for Product B.")
    client.post(
        f"/api/v1/products/{product_a['id']}/evidence",
        json={"evidence_id": evidence_about_b["id"], "claim": "Product A is Grade A"},
        headers=org["headers"],
    )

    rec = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "persist": False}, headers=org["headers"],
    ).json()["recommendations"][0]
    assert rec["evidence_state"] == "unknown"
    assert rec["evidence_score"] == 0.5


def test_verifying_a_mismatched_link_is_recorded_against_a_named_actor(
    client: TestClient, register_org
) -> None:
    """If a human DOES verify a mismatched pairing, the system's
    guarantee is attribution, not prevention. This test exists to make
    that limit explicit and permanent rather than discovered later."""
    org = register_org()
    product_a = _product(client, org["headers"], "product-a", "Product A")
    evidence_about_b = _verified_evidence(client, org["headers"], "Lab report for Product B.")
    link = client.post(
        f"/api/v1/products/{product_a['id']}/evidence",
        json={"evidence_id": evidence_about_b["id"], "claim": "Product A is Grade A"},
        headers=org["headers"],
    ).json()

    verified = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified", "note": "checked by hand"},
        headers=org["headers"],
    )
    # It succeeds - the system cannot judge semantic fit.
    assert verified.status_code == 200
    assert verified.json()["verified_at"] is not None
    # But the claim text travels with the link, so the mismatch is
    # visible to any later reviewer reading the record.
    assert verified.json()["claim"] == "Product A is Grade A"


def test_trust_record_evidence_is_not_semantically_bound_to_its_subject(
    client: TestClient, register_org
) -> None:
    """Same limit on the trust side, pinned down explicitly."""
    org = register_org()
    product_a = _product(client, org["headers"], "product-a", "Product A")
    _product(client, org["headers"], "product-b", "Product B")
    evidence_about_b = _verified_evidence(client, org["headers"], "Certificate for Product B.")

    record = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_a["id"], "trust_type": "certification",
            "claim": "Product A is certified", "evidence_id": evidence_about_b["id"],
        },
        headers=org["headers"],
    )
    assert record.status_code == 201
    assert record.json()["verification_status"] == "unverified"
