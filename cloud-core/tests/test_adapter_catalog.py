"""
Tests for GET /adapter/catalog/{id} — the read projection added in Phase 9
so the WordPress adapter can render JSON-LD (ADR-042).

The safety property under test: **the projection carries no evidence or
trust data.** An adapter that could read verified claims could publish them
as public structured-data assertions, and structured data is a public claim.
The simplest guarantee is not to hand it the material at all.
"""

from fastapi.testclient import TestClient


def _published_product(client: TestClient, headers: dict, slug: str = "p", **offer_kw) -> dict:
    product = client.post(
        "/api/v1/products",
        json={"name": "Taranjabin 500g", "slug": slug, "brand": "BrandX", "category": "sweeteners"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=headers)
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=headers)
    payload = {"price": 100, "currency": "EUR", "availability": "in_stock"}
    payload.update(offer_kw)
    client.post(f"/api/v1/products/{product['id']}/offers", json=payload, headers=headers)
    return product


def _adapter_token(client: TestClient, headers: dict, scopes=None) -> str:
    site = client.post(
        "/api/v1/sites", json={"name": "S", "domain": "a.example"}, headers=headers
    ).json()
    inst = client.post(
        "/api/v1/installations",
        json={"name": "WP", "adapter_type": "wordpress", "site_id": site["id"]},
        headers=headers,
    ).json()
    return client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": scopes or ["catalog:read"]},
        headers=headers,
    ).json()["token"]


def _m(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_catalog_returns_product_identity_and_offer(client: TestClient, register_org) -> None:
    org = register_org()
    product = _published_product(client, org["headers"])
    token = _adapter_token(client, org["headers"])

    response = client.get(f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Taranjabin 500g"
    assert body["status"] == "published"
    assert body["offer"]["price"] == 100
    assert body["offer"]["availability"] == "in_stock"


def test_catalog_never_exposes_evidence_or_trust(client: TestClient, register_org) -> None:
    """The central safety assertion of this endpoint."""
    org = register_org()
    product = _published_product(client, org["headers"])
    token = _adapter_token(client, org["headers"])

    body = client.get(f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token)).json()
    for forbidden in ("evidence", "trust", "claims", "verification_status", "recommendation"):
        assert forbidden not in body, f"adapter projection must not carry '{forbidden}'"


def test_price_on_request_is_null_not_zero(client: TestClient, register_org) -> None:
    """The null-vs-zero distinction must survive into the adapter."""
    org = register_org()
    product = client.post(
        "/api/v1/products", json={"name": "Quote only", "slug": "q"}, headers=org["headers"]
    ).json()
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=org["headers"])
    client.post(f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=org["headers"])
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"availability": "in_stock"}, headers=org["headers"],
    )
    token = _adapter_token(client, org["headers"])

    body = client.get(f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token)).json()
    assert body["offer"] is not None
    assert body["offer"]["price"] is None  # never 0


def test_out_of_stock_product_reports_no_purchasable_offer(client: TestClient, register_org) -> None:
    org = register_org()
    product = _published_product(client, org["headers"], availability="out_of_stock")
    token = _adapter_token(client, org["headers"])

    body = client.get(f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token)).json()
    assert body["offer"] is None


def test_draft_product_is_readable_but_reports_its_real_status(client: TestClient, register_org) -> None:
    """Core reports the truth; the adapter is responsible for not
    publishing a non-published product (tested on the PHP side)."""
    org = register_org()
    product = client.post(
        "/api/v1/products", json={"name": "Draft", "slug": "d"}, headers=org["headers"]
    ).json()
    token = _adapter_token(client, org["headers"])

    body = client.get(f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token)).json()
    assert body["status"] == "draft"


def test_catalog_requires_catalog_read_scope(client: TestClient, register_org) -> None:
    org = register_org()
    product = _published_product(client, org["headers"])
    token = _adapter_token(client, org["headers"], scopes=["mappings:read"])

    assert client.get(
        f"/api/v1/adapter/catalog/{product['id']}", headers=_m(token)
    ).status_code == 403


def test_catalog_cannot_read_another_orgs_product(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    product_b = _published_product(client, org_b["headers"], slug="b")
    token_a = _adapter_token(client, org_a["headers"])

    assert client.get(
        f"/api/v1/adapter/catalog/{product_b['id']}", headers=_m(token_a)
    ).status_code == 404


def test_catalog_requires_authentication(client: TestClient, register_org) -> None:
    org = register_org()
    product = _published_product(client, org["headers"])
    assert client.get(f"/api/v1/adapter/catalog/{product['id']}").status_code == 401
