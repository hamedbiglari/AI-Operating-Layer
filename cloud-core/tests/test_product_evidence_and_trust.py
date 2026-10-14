"""
Adversarial tests for the two safety rules Phase 7 exists to enforce:

1. **Evidence scope** — composition evidence must not silently become
   clinical-efficacy evidence (the Taranjabin/Mannitol case).
2. **No fake trust** — trust must be evidence-backed and never
   auto-verified (master spec section 30).

These are written as attacks: each asks "can the system be made to do
the forbidden thing?" rather than "does the happy path work?"
"""

from fastapi.testclient import TestClient


def _product(client: TestClient, headers: dict, slug: str = "taranjabin") -> dict:
    return client.post(
        "/api/v1/products", json={"name": "Taranjabin 500g", "slug": slug}, headers=headers
    ).json()


def _evidence(
    client: TestClient, headers: dict, summary: str, strength: str = "high", verify: bool = True
) -> dict:
    """Creates an Evidence row and, by default, verifies it.

    The default changed when the two-layer verification invariant
    landed (ADR-032): a product-evidence link or trust record can only
    be marked verified when the Evidence beneath it is verified too, so
    tests that want to exercise the verified path must establish that
    precondition explicitly. Pass `verify=False` to keep the Evidence
    in DRAFT."""
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "Mannitol RCT"},
        headers=headers,
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "evidence_strength": strength, "summary": summary},
        headers=headers,
    ).json()
    if verify:
        evidence = client.post(
            f"/api/v1/evidence/{evidence['id']}/review",
            json={"status": "verified"}, headers=headers,
        ).json()
    return evidence


# --- Evidence scope --------------------------------------------------------


def test_evidence_link_requires_an_explicit_claim(client: TestClient, register_org) -> None:
    """The scope guarantee: a piece of evidence cannot be attached to a
    product without naming what it is evidence FOR. An unscoped link is
    unrepresentable at the API layer."""
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Mannitol reduced symptom X in an RCT.")

    response = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"]},  # no claim
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_empty_claim_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Some finding.")

    response = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": ""},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_compound_evidence_does_not_auto_verify_a_clinical_claim(client: TestClient, register_org) -> None:
    """THE central adversarial case. A study about Mannitol is linked
    to a Taranjabin product. Even though the evidence row itself is
    VERIFIED and HIGH strength, the product-level link starts
    UNVERIFIED — the system does not infer that the product inherits
    the compound's clinical effect."""
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Mannitol reduced symptom X in an RCT (N=200).")
    # The underlying Evidence row IS verified at the Phase 4 level -
    # which makes this the strongest possible version of the test: even
    # a fully verified study does not verify the product-level clinical
    # claim it is cited for.
    assert evidence["status"] == "verified"

    link = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={
            "evidence_id": evidence["id"],
            "claim": "Taranjabin 500g relieves symptom X clinically",
        },
        headers=org["headers"],
    )
    assert link.status_code == 201, link.text
    body = link.json()
    # Phase 4 verification of the STUDY does not verify the
    # PRODUCT-LEVEL claim that study is being cited for.
    assert body["verification_status"] == "unverified"
    assert body["verified_at"] is None


def test_same_evidence_can_support_two_different_claims_independently(
    client: TestClient, register_org
) -> None:
    """Scope is per-claim: one lab report can evidence 'Grade = A' and
    'no heavy metals' as two separate, separately-verifiable links —
    verifying one must not verify the other."""
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Lab report #123.")

    grade_link = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": "Grade = A"},
        headers=org["headers"],
    ).json()
    metals_link = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": "No heavy metals detected"},
        headers=org["headers"],
    ).json()
    assert grade_link["id"] != metals_link["id"]

    client.post(
        f"/api/v1/product-evidence/{grade_link['id']}/verify",
        json={"verification_status": "verified"},
        headers=org["headers"],
    )

    listing = client.get(f"/api/v1/products/{product['id']}/evidence", headers=org["headers"]).json()
    by_claim = {item["claim"]: item for item in listing["items"]}
    assert by_claim["Grade = A"]["verification_status"] == "verified"
    assert by_claim["No heavy metals detected"]["verification_status"] == "unverified"


def test_duplicate_identical_claim_link_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Lab report.")
    client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": "Grade = A"},
        headers=org["headers"],
    )

    response = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": "Grade = A"},
        headers=org["headers"],
    )
    assert response.status_code == 409


def test_verification_can_be_revoked_and_clears_verified_at(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Lab report.")
    link = client.post(
        f"/api/v1/products/{product['id']}/evidence",
        json={"evidence_id": evidence["id"], "claim": "Grade = A"},
        headers=org["headers"],
    ).json()

    verified = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"},
        headers=org["headers"],
    ).json()
    assert verified["verified_at"] is not None

    rejected = client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "rejected", "note": "Report does not support this grade."},
        headers=org["headers"],
    ).json()
    assert rejected["verification_status"] == "rejected"
    assert rejected["verified_at"] is None


def test_cannot_link_another_orgs_evidence_to_own_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_a = _product(client, org_a["headers"])
    evidence_b = _evidence(client, org_b["headers"], "B's evidence.")

    response = client.post(
        f"/api/v1/products/{product_a['id']}/evidence",
        json={"evidence_id": evidence_b["id"], "claim": "Grade = A"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


# --- Trust: no fake trust --------------------------------------------------


def test_trust_record_without_evidence_is_rejected(client: TestClient, register_org) -> None:
    """Section 30: 'Trust must be evidence-backed.' A trust assertion
    with no evidence_id cannot be expressed at all."""
    org = register_org()
    product = _product(client, org["headers"])

    response = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product",
            "subject_id": product["id"],
            "trust_type": "quality",
            "claim": "This product is high quality",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_trust_record_starts_unverified(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    evidence = _evidence(client, org["headers"], "Quality inspection report.")

    response = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product",
            "subject_id": product["id"],
            "trust_type": "quality",
            "claim": "Passed quality inspection",
            "evidence_id": evidence["id"],
        },
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_status"] == "unverified"
    assert body["verified_at"] is None
    # Section 30: there is deliberately no score.
    assert "trust_score" not in body
    assert "score" not in body


def test_trust_record_cannot_target_another_orgs_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    evidence_a = _evidence(client, org_a["headers"], "A's evidence.")

    response = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product",
            "subject_id": product_b["id"],
            "trust_type": "quality",
            "claim": "Attempted cross-tenant trust",
            "evidence_id": evidence_a["id"],
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_trust_record_cannot_target_another_organization(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    evidence_a = _evidence(client, org_a["headers"], "A's evidence.")

    response = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "organization",
            "subject_id": org_b["organization"]["id"],
            "trust_type": "business_identity",
            "claim": "Attempted trust assertion about another company",
            "evidence_id": evidence_a["id"],
        },
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_trust_record_about_own_organization_is_allowed(client: TestClient, register_org) -> None:
    org = register_org()
    evidence = _evidence(client, org["headers"], "Business registration certificate.")

    response = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "organization",
            "subject_id": org["organization"]["id"],
            "trust_type": "business_identity",
            "claim": "Registered business #12345",
            "evidence_id": evidence["id"],
        },
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text


def test_verified_trust_is_filterable_so_trust_is_enumerable_not_scored(
    client: TestClient, register_org
) -> None:
    """'How trusted is this product' is answered by enumerating
    VERIFIED rows, not by reading a score — this proves that query
    works."""
    org = register_org()
    product = _product(client, org["headers"])
    ev1 = _evidence(client, org["headers"], "Origin document.")
    ev2 = _evidence(client, org["headers"], "Lab report.")

    r1 = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product["id"], "trust_type": "origin",
            "claim": "Origin = Iran", "evidence_id": ev1["id"],
        },
        headers=org["headers"],
    ).json()
    client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": ev2["id"],
        },
        headers=org["headers"],
    )
    client.post(
        f"/api/v1/trust-records/{r1['id']}/verify",
        json={"verification_status": "verified"},
        headers=org["headers"],
    )

    verified = client.get(
        f"/api/v1/trust-records?subject_id={product['id']}&verification_status=verified",
        headers=org["headers"],
    ).json()
    assert verified["total"] == 1
    assert verified["items"][0]["claim"] == "Origin = Iran"

    everything = client.get(
        f"/api/v1/trust-records?subject_id={product['id']}", headers=org["headers"]
    ).json()
    assert everything["total"] == 2
