"""
Integration tests for /products/{id}/offers and
/products/{id}/related — including the deliberate semantic split
between "stock untracked" (NULL) and "none in stock" (0), and the
non-mirroring of directional relations.
"""

from fastapi.testclient import TestClient


def _product(client: TestClient, headers: dict, slug: str = "taranjabin", name: str = "Taranjabin") -> dict:
    return client.post("/api/v1/products", json={"name": name, "slug": slug}, headers=headers).json()


# --- Offers -----------------------------------------------------------------


def test_create_offer_for_product(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])

    response = client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"price": 250000, "currency": "IRR", "availability": "in_stock", "stock_quantity": 40},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["product_id"] == product["id"]
    assert body["price"] == 250000
    assert body["condition"] == "new"


def test_one_product_can_have_multiple_simultaneous_offers(client: TestClient, register_org) -> None:
    """Section 27's whole reason for existing: different price/currency/
    seller/promotion for the same product at the same time."""
    org = register_org()
    product = _product(client, org["headers"])
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"price": 250000, "currency": "IRR"},
        headers=org["headers"],
    )
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"price": 12, "currency": "EUR"},
        headers=org["headers"],
    )

    offers = client.get(f"/api/v1/products/{product['id']}/offers", headers=org["headers"]).json()
    assert offers["total"] == 2


def test_null_stock_quantity_is_not_out_of_stock(client: TestClient, register_org) -> None:
    """NULL means 'quantity untracked', which must not be collapsed
    into 0 ('tracked, and there are none')."""
    org = register_org()
    product = _product(client, org["headers"])

    untracked = client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"availability": "in_stock"},
        headers=org["headers"],
    ).json()
    assert untracked["stock_quantity"] is None
    assert untracked["availability"] == "in_stock"

    none_left = client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"availability": "out_of_stock", "stock_quantity": 0, "external_id": "second"},
        headers=org["headers"],
    ).json()
    assert none_left["stock_quantity"] == 0
    assert none_left["availability"] == "out_of_stock"


def test_price_on_request_is_representable(client: TestClient, register_org) -> None:
    """A NULL price ('contact for quote') is a real B2B state and is
    different from a price of zero."""
    org = register_org()
    product = _product(client, org["headers"])

    response = client.post(
        f"/api/v1/products/{product['id']}/offers", json={"availability": "in_stock"}, headers=org["headers"]
    )
    assert response.status_code == 201
    assert response.json()["price"] is None


def test_negative_price_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])

    response = client.post(
        f"/api/v1/products/{product['id']}/offers", json={"price": -5, "currency": "EUR"}, headers=org["headers"]
    )
    assert response.status_code == 422


def test_update_offer_availability(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    offer = client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"price": 100, "currency": "EUR", "availability": "in_stock", "stock_quantity": 5},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/offers/{offer['id']}",
        json={"availability": "out_of_stock", "stock_quantity": 0},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["availability"] == "out_of_stock"


def test_filter_offers_by_availability(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"])
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"availability": "in_stock", "external_id": "a"},
        headers=org["headers"],
    )
    client.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"availability": "out_of_stock", "external_id": "b"},
        headers=org["headers"],
    )

    in_stock = client.get(
        f"/api/v1/products/{product['id']}/offers?availability=in_stock", headers=org["headers"]
    ).json()
    assert in_stock["total"] == 1


# --- Product Relations ---------------------------------------------------------


def test_create_product_relation(client: TestClient, register_org) -> None:
    org = register_org()
    a = _product(client, org["headers"], slug="a", name="Product A")
    b = _product(client, org["headers"], slug="b", name="Product B")

    response = client.post(
        f"/api/v1/products/{a['id']}/related",
        json={"related_product_id": b["id"], "relation_type": "alternative", "confidence": 0.8},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["relation_type"] == "alternative"


def test_relation_is_not_auto_mirrored(client: TestClient, register_org) -> None:
    """'B replaces A' does not imply 'A replaces B' — the system does
    not guess which relation types happen to be symmetric."""
    org = register_org()
    a = _product(client, org["headers"], slug="a", name="Product A")
    b = _product(client, org["headers"], slug="b", name="Product B")
    client.post(
        f"/api/v1/products/{a['id']}/related",
        json={"related_product_id": b["id"], "relation_type": "replacement"},
        headers=org["headers"],
    )

    reverse = client.get(f"/api/v1/products/{b['id']}/related", headers=org["headers"]).json()
    assert reverse["total"] == 0


def test_self_relation_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    a = _product(client, org["headers"], slug="a", name="Product A")

    response = client.post(
        f"/api/v1/products/{a['id']}/related",
        json={"related_product_id": a["id"], "relation_type": "similar"},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_duplicate_relation_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    a = _product(client, org["headers"], slug="a", name="Product A")
    b = _product(client, org["headers"], slug="b", name="Product B")
    payload = {"related_product_id": b["id"], "relation_type": "similar"}
    client.post(f"/api/v1/products/{a['id']}/related", json=payload, headers=org["headers"])

    response = client.post(f"/api/v1/products/{a['id']}/related", json=payload, headers=org["headers"])
    assert response.status_code == 409


def test_cannot_relate_to_another_orgs_product(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    a = _product(client, org_a["headers"], slug="a", name="A")
    b = _product(client, org_b["headers"], slug="b", name="B")

    response = client.post(
        f"/api/v1/products/{a['id']}/related",
        json={"related_product_id": b["id"], "relation_type": "similar"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404
