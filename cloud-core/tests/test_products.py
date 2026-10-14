"""
Integration tests for /products — creation, uniqueness, the status
lifecycle (never auto-published), and cross-resource tenant validation.
"""

from fastapi.testclient import TestClient


def _create_product(client: TestClient, headers: dict, **overrides) -> dict:
    payload = {"name": "Taranjabin 500g", "slug": "taranjabin-500g"}
    payload.update(overrides)
    return client.post("/api/v1/products", json=payload, headers=headers)


def test_create_product_starts_as_draft(client: TestClient, register_org) -> None:
    org = register_org()
    response = _create_product(client, org["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["provenance"] == "merchant"
    # Section 27: price/stock must NOT live on Product.
    assert "price" not in body
    assert "stock_quantity" not in body


def test_duplicate_slug_in_same_org_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    _create_product(client, org["headers"])
    response = _create_product(client, org["headers"], name="Another name")
    assert response.status_code == 409


def test_duplicate_sku_in_same_org_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    _create_product(client, org["headers"], sku="SKU-1")
    response = _create_product(client, org["headers"], slug="other-slug", sku="SKU-1")
    assert response.status_code == 409


def test_same_sku_allowed_across_different_orgs(client: TestClient, register_org) -> None:
    """SKUs are unique per merchant, not globally — two unrelated
    merchants legitimately use the same SKU string."""
    org_a = register_org()
    org_b = register_org()
    first = _create_product(client, org_a["headers"], sku="SHARED-SKU")
    second = _create_product(client, org_b["headers"], sku="SHARED-SKU")
    assert first.status_code == 201
    assert second.status_code == 201


def test_product_cannot_reference_another_orgs_knowledge_object(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    ko_b = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=org_b["headers"],
    ).json()

    response = _create_product(client, org_a["headers"], knowledge_object_id=ko_b["id"])
    assert response.status_code == 404


def test_product_cannot_reference_another_orgs_site(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    site_b = client.post(
        "/api/v1/sites", json={"name": "B Store", "domain": "b-store.example"}, headers=org_b["headers"]
    ).json()

    response = _create_product(client, org_a["headers"], site_id=site_b["id"])
    assert response.status_code == 404


def test_product_links_to_knowledge_object_without_copying_it(client: TestClient, register_org) -> None:
    """The Phase 7 rule: 'Avoid copying the entire Knowledge Object
    into Product.' The product carries a pointer, not the content."""
    org = register_org()
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=org["headers"],
    ).json()

    response = _create_product(client, org["headers"], knowledge_object_id=ko["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["knowledge_object_id"] == ko["id"]
    # No knowledge content was duplicated onto the product.
    assert "canonical_name" not in body
    assert "claims" not in body


def test_product_cannot_jump_straight_from_draft_to_published(client: TestClient, register_org) -> None:
    """Section 44 discipline, inherited because a Product IS a
    normalized Product Knowledge Object (section 26)."""
    org = register_org()
    product = _create_product(client, org["headers"]).json()

    response = client.post(
        f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=org["headers"]
    )
    assert response.status_code == 422


def test_full_publication_lifecycle(client: TestClient, register_org) -> None:
    org = register_org()
    product = _create_product(client, org["headers"]).json()

    in_review = client.post(
        f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=org["headers"]
    )
    assert in_review.status_code == 200
    assert in_review.json()["status"] == "in_review"

    published = client.post(
        f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=org["headers"]
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    archived = client.post(
        f"/api/v1/products/{product['id']}/status", json={"status": "archived"}, headers=org["headers"]
    )
    assert archived.status_code == 200


def test_patch_cannot_change_status(client: TestClient, register_org) -> None:
    """A plain field edit must never silently publish a product."""
    org = register_org()
    product = _create_product(client, org["headers"]).json()

    response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"name": "Renamed", "status": "published"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["status"] == "draft"  # unchanged — status is not a PATCH field


def test_update_product_fields(client: TestClient, register_org) -> None:
    org = register_org()
    product = _create_product(client, org["headers"]).json()

    response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"category": "sweeteners", "certifications": {"organic": "cert-123"}},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "sweeteners"
    assert body["certifications"] == {"organic": "cert-123"}


def test_list_products_filtered(client: TestClient, register_org) -> None:
    org = register_org()
    _create_product(client, org["headers"], category="sweeteners")
    _create_product(client, org["headers"], slug="other", name="Other", category="herbs")

    response = client.get("/api/v1/products?category=sweeteners", headers=org["headers"])
    assert response.json()["total"] == 1


def test_viewer_cannot_create_product(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={"email": "prod-viewer@example.dev", "name": "Viewer", "password": "supersecret123", "role": "viewer"},
        headers=org["headers"],
    )
    login = client.post(
        "/api/v1/auth/login", data={"username": "prod-viewer@example.dev", "password": "supersecret123"}
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = _create_product(client, viewer_headers)
    assert response.status_code == 403
