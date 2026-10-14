"""
THE GOLDEN TEST SUITE — Phase 8 edition (Customer Context &
Recommendation).

Phase 8 is the first genuinely cross-domain consumer, so the
cross-tenant surface is larger than in any prior phase: a
recommendation touches products, offers, evidence, trust, contexts and
queries at once. The single most important case is the two-hop one:

    Tenant A's product + Tenant B's evidence
    MUST NEVER become a valid recommendation.
"""

from fastapi.testclient import TestClient


def _published_product(client: TestClient, headers: dict, slug: str = "p") -> dict:
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


def _context(client: TestClient, headers: dict) -> dict:
    return client.post("/api/v1/context", json={"source": "web"}, headers=headers).json()


# --- Customer Context ------------------------------------------------------


def test_user_cannot_read_another_orgs_context(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    context_b = _context(client, org_b["headers"])
    assert client.get(f"/api/v1/context/{context_b['id']}", headers=org_a["headers"]).status_code == 404


def test_user_cannot_update_another_orgs_context(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    context_b = _context(client, org_b["headers"])
    response = client.patch(
        f"/api/v1/context/{context_b['id']}", json={"topic": "hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_withdraw_consent_on_another_orgs_context(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    context_b = _context(client, org_b["headers"])
    response = client.post(
        f"/api/v1/context/{context_b['id']}/withdraw-consent", headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_context_list_never_includes_other_orgs_contexts(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _context(client, org_a["headers"])
    _context(client, org_b["headers"])
    assert client.get("/api/v1/context", headers=org_a["headers"]).json()["total"] == 1


# --- Recommendation: the cross-domain cases --------------------------------


def test_recommendation_never_includes_another_orgs_product(client: TestClient, register_org) -> None:
    """The most basic leak, and the one with the worst consequences."""
    org_a, org_b = register_org(), register_org()
    _published_product(client, org_b["headers"], "b-product")

    body = client.post(
        "/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_a["headers"]
    ).json()
    assert body["recommendations"] == []
    assert body["rejected"] == []  # org B's product is not even a candidate


def test_explicitly_requesting_another_orgs_product_id_returns_nothing(
    client: TestClient, register_org
) -> None:
    """Two-hop: fully authenticated as A, but naming B's product id."""
    org_a, org_b = register_org(), register_org()
    product_b = _published_product(client, org_b["headers"], "b-product")

    body = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "product_ids": [product_b["id"]]},
        headers=org_a["headers"],
    ).json()
    assert body["status"] == "no_recommendation"
    assert body["recommendations"] == []


def test_another_orgs_evidence_cannot_raise_own_products_score(
    client: TestClient, register_org
) -> None:
    """Tenant A's product + Tenant B's verified evidence must never
    combine. The evidence summary contract is org-scoped at the source,
    so B's verified claims are invisible to A's scoring."""
    org_a, org_b = register_org(), register_org()
    product_a = _published_product(client, org_a["headers"], "a-product")

    # org B builds a heavily-evidenced product
    product_b = _published_product(client, org_b["headers"], "b-product")
    for claim in ("Grade = A", "Origin = Iran", "Lab tested"):
        source = client.post(
            "/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"},
            headers=org_b["headers"],
        ).json()
        ev = client.post(
            "/api/v1/evidence", json={"source_id": source["id"], "summary": "x"},
            headers=org_b["headers"],
        ).json()
        link = client.post(
            f"/api/v1/products/{product_b['id']}/evidence",
            json={"evidence_id": ev["id"], "claim": claim}, headers=org_b["headers"],
        ).json()
        client.post(
            f"/api/v1/product-evidence/{link['id']}/verify",
            json={"verification_status": "verified"}, headers=org_b["headers"],
        )

    body = client.post(
        "/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_a["headers"]
    ).json()
    rec = body["recommendations"][0]
    assert rec["product_id"] == product_a["id"]
    # A's product has no evidence of its own; B's must not leak in.
    assert rec["evidence_state"] == "unknown"


def test_another_orgs_trust_cannot_raise_own_products_score(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    product_a = _published_product(client, org_a["headers"], "a-product")
    product_b = _published_product(client, org_b["headers"], "b-product")

    source = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "S"}, headers=org_b["headers"]
    ).json()
    ev = client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": "x"}, headers=org_b["headers"]
    ).json()
    record = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_b["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": ev["id"],
        },
        headers=org_b["headers"],
    ).json()
    client.post(
        f"/api/v1/trust-records/{record['id']}/verify",
        json={"verification_status": "verified"}, headers=org_b["headers"],
    )

    body = client.post(
        "/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_a["headers"]
    ).json()
    rec = body["recommendations"][0]
    assert rec["product_id"] == product_a["id"]
    assert rec["trust_state"] == "unknown"


def test_cannot_recommend_against_another_orgs_context(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _published_product(client, org_a["headers"], "a-product")
    context_b = _context(client, org_b["headers"])

    response = client.post(
        "/api/v1/recommendations",
        json={"response_mode": "recommend", "customer_context_id": context_b["id"]},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_recommendation(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _published_product(client, org_b["headers"], "b-product")
    rec_b = client.post(
        "/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_b["headers"]
    ).json()["recommendations"][0]

    assert client.get(
        f"/api/v1/recommendations/{rec_b['id']}", headers=org_a["headers"]
    ).status_code == 404


def test_recommendation_list_never_includes_other_orgs_rows(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _published_product(client, org_a["headers"], "a-product")
    _published_product(client, org_b["headers"], "b-product")
    client.post("/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_a["headers"])
    client.post("/api/v1/recommendations", json={"response_mode": "recommend"}, headers=org_b["headers"])

    listing = client.get("/api/v1/recommendations", headers=org_a["headers"]).json()
    assert listing["total"] == 1
    assert listing["items"][0]["organization_id"] == org_a["organization"]["id"]


def test_viewer_cannot_generate_recommendations(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={"email": "rec-viewer@example.dev", "name": "V", "password": "supersecret123", "role": "viewer"},
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login", data={"username": "rec-viewer@example.dev", "password": "supersecret123"}
    )
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/recommendations", json={"response_mode": "recommend"}, headers=viewer
    )
    assert response.status_code == 403
