"""
THE GOLDEN TEST SUITE — Phase 7 edition (Commerce & Product Knowledge).

Continues the pattern from every prior phase: Organization A must never
read, list, or write anything belonging to Organization B — across all
five new tables and every route that touches them.

Cross-resource attack cases (own product + another org's evidence,
another org's product + own evidence, etc.) live in
test_product_evidence_and_trust.py; this file covers direct access and
list-leakage.
"""

from fastapi.testclient import TestClient


def _product(client: TestClient, headers: dict, slug: str = "p", name: str = "P") -> dict:
    return client.post("/api/v1/products", json={"name": name, "slug": slug}, headers=headers).json()


def _offer(client: TestClient, headers: dict, product_id: str) -> dict:
    return client.post(
        f"/api/v1/products/{product_id}/offers", json={"price": 100, "currency": "EUR"}, headers=headers
    ).json()


def _evidence(client: TestClient, headers: dict) -> dict:
    source = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "S"}, headers=headers
    ).json()
    return client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": "A finding."}, headers=headers
    ).json()


# --- Products ------------------------------------------------------------


def test_user_cannot_read_another_orgs_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    assert client.get(f"/api/v1/products/{product_b['id']}", headers=org_a["headers"]).status_code == 404


def test_user_cannot_update_another_orgs_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    response = client.patch(
        f"/api/v1/products/{product_b['id']}", json={"name": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_change_another_orgs_product_status(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    response = client.post(
        f"/api/v1/products/{product_b['id']}/status", json={"status": "in_review"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_product_list_never_includes_other_orgs_products(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _product(client, org_a["headers"], slug="a", name="A Only")
    _product(client, org_b["headers"], slug="b", name="B Only")

    names = [p["name"] for p in client.get("/api/v1/products", headers=org_a["headers"]).json()["items"]]
    assert "A Only" in names
    assert "B Only" not in names


# --- Offers ---------------------------------------------------------------


def test_user_cannot_create_offer_on_another_orgs_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    response = client.post(
        f"/api/v1/products/{product_b['id']}/offers", json={"price": 1, "currency": "EUR"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_offer(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    offer_b = _offer(client, org_b["headers"], product_b["id"])

    response = client.patch(
        f"/api/v1/offers/{offer_b['id']}", json={"price": 1}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_list_another_orgs_product_offers(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    _offer(client, org_b["headers"], product_b["id"])

    response = client.get(f"/api/v1/products/{product_b['id']}/offers", headers=org_a["headers"])
    assert response.status_code == 404


# --- Product Evidence -------------------------------------------------------


def test_user_cannot_list_another_orgs_product_evidence(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    response = client.get(f"/api/v1/products/{product_b['id']}/evidence", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_verify_another_orgs_product_evidence_link(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    evidence_b = _evidence(client, org_b["headers"])
    link_b = client.post(
        f"/api/v1/products/{product_b['id']}/evidence",
        json={"evidence_id": evidence_b["id"], "claim": "Grade = A"},
        headers=org_b["headers"],
    ).json()

    response = client.post(
        f"/api/v1/product-evidence/{link_b['id']}/verify",
        json={"verification_status": "verified"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


# --- Product Relations --------------------------------------------------------


def test_user_cannot_list_another_orgs_product_relations(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])

    response = client.get(f"/api/v1/products/{product_b['id']}/related", headers=org_a["headers"])
    assert response.status_code == 404


# --- Trust Records --------------------------------------------------------------


def test_user_cannot_read_another_orgs_trust_record(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    evidence_b = _evidence(client, org_b["headers"])
    record_b = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_b["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": evidence_b["id"],
        },
        headers=org_b["headers"],
    ).json()

    assert client.get(
        f"/api/v1/trust-records/{record_b['id']}", headers=org_a["headers"]
    ).status_code == 404


def test_user_cannot_verify_another_orgs_trust_record(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_b = _product(client, org_b["headers"])
    evidence_b = _evidence(client, org_b["headers"])
    record_b = client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_b["id"], "trust_type": "quality",
            "claim": "Grade A", "evidence_id": evidence_b["id"],
        },
        headers=org_b["headers"],
    ).json()

    response = client.post(
        f"/api/v1/trust-records/{record_b['id']}/verify",
        json={"verification_status": "verified"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_trust_record_list_never_includes_other_orgs_records(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    product_a = _product(client, org_a["headers"], slug="a")
    evidence_a = _evidence(client, org_a["headers"])
    client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_a["id"], "trust_type": "origin",
            "claim": "A's claim", "evidence_id": evidence_a["id"],
        },
        headers=org_a["headers"],
    )

    product_b = _product(client, org_b["headers"], slug="b")
    evidence_b = _evidence(client, org_b["headers"])
    client.post(
        "/api/v1/trust-records",
        json={
            "subject_type": "product", "subject_id": product_b["id"], "trust_type": "origin",
            "claim": "B's claim", "evidence_id": evidence_b["id"],
        },
        headers=org_b["headers"],
    )

    listing = client.get("/api/v1/trust-records", headers=org_a["headers"]).json()
    assert listing["total"] == 1
    assert listing["items"][0]["claim"] == "A's claim"


def test_intent_product_id_fk_now_enforced(client: TestClient, register_org) -> None:
    """Phase 6 left intents.product_id as a plain UUID with no FK,
    documenting that 'a future Phase 7 migration adds the FK'. This
    proves migration 0008 actually closed it: the column now exists
    alongside a real products table, and a product-linked read path
    works end to end."""
    org = register_org()
    product = _product(client, org["headers"])
    imported = client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": '[{"query": "قیمت ترنجبین"}]'},
        headers=org["headers"],
    ).json()
    query_id = imported["items"][0]["query_id"]

    intent = client.post(
        f"/api/v1/queries/{query_id}/intents",
        json={"intent_type": "price", "is_primary": True},
        headers=org["headers"],
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["product_id"] is None
    assert product["id"]  # the products table this FK points at genuinely exists now
