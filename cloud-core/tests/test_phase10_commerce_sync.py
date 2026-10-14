"""
Phase 10 — WooCommerce commerce sync.

The adversarial tests are the point. Each asks: **can WooCommerce be made
to change something it must not own?**

Directional rule under test (ADR-050):
    WooCommerce MAY update an Offer's price/stock/availability.
    WooCommerce MAY NOT touch Product identity, status, evidence, trust,
    or any recommendation.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError


def _setup(client: TestClient, headers: dict, slug: str = "p", publish: bool = True) -> dict:
    site = client.post(
        "/api/v1/sites", json={"name": "Shop", "domain": f"{slug}.example"}, headers=headers
    ).json()
    product = client.post(
        "/api/v1/products", json={"name": "Taranjabin", "slug": slug}, headers=headers
    ).json()
    if publish:
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=headers)
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=headers)
    inst = client.post(
        "/api/v1/installations",
        json={"name": "Woo", "adapter_type": "wordpress", "site_id": site["id"]},
        headers=headers,
    ).json()
    token = client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": ["commerce:read", "commerce:write", "catalog:read"]},
        headers=headers,
    ).json()["token"]
    return {"site": site, "product": product, "installation": inst, "token": token}


def _m(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _map(client: TestClient, token: str, product_id: str, woo_id: int = 101, **kw) -> dict:
    payload = {"product_id": product_id, "woo_product_id": woo_id}
    payload.update(kw)
    return client.post("/api/v1/adapter/commerce/mappings", json=payload, headers=_m(token))


# --- Mapping & idempotency ---------------------------------------------------


def test_mapping_is_created_then_idempotent(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    first = _map(client, ctx["token"], ctx["product"]["id"])
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True

    repeats = [_map(client, ctx["token"], ctx["product"]["id"]).json() for _ in range(4)]
    assert all(r["created"] is False for r in repeats)
    assert len({r["mapping"]["id"] for r in repeats}) == 1


def test_repointing_woo_product_to_a_different_core_product_is_409(
    client: TestClient, register_org
) -> None:
    """Silently rewriting this would move a merchant's evidence and trust
    history onto another product."""
    org = register_org()
    ctx = _setup(client, org["headers"])
    other = client.post(
        "/api/v1/products", json={"name": "Other", "slug": "other"}, headers=org["headers"]
    ).json()
    _map(client, ctx["token"], ctx["product"]["id"], woo_id=555)

    response = _map(client, ctx["token"], other["id"], woo_id=555)
    assert response.status_code == 409


def test_variation_and_simple_product_do_not_collide(client: TestClient, register_org) -> None:
    """NULLS NOT DISTINCT earning its keep: a simple product (NULL
    variation) and a variation must be separable."""
    org = register_org()
    ctx = _setup(client, org["headers"])
    v1 = _map(client, ctx["token"], ctx["product"]["id"], woo_id=700, woo_variation_id=1)
    v2 = _map(client, ctx["token"], ctx["product"]["id"], woo_id=700, woo_variation_id=2)
    assert v1.status_code == 200 and v2.status_code == 200
    assert v1.json()["mapping"]["id"] != v2.json()["mapping"]["id"]


def test_two_simple_products_cannot_claim_the_same_woo_id(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    other = client.post(
        "/api/v1/products", json={"name": "Other", "slug": "other2"}, headers=org["headers"]
    ).json()
    _map(client, ctx["token"], ctx["product"]["id"], woo_id=900)
    response = _map(client, ctx["token"], other["id"], woo_id=900)
    assert response.status_code == 409


# --- Offer sync: the only permitted write ---------------------------------------


def test_offer_sync_updates_price_and_stock(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]

    response = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer",
        json={"price": 250, "currency": "EUR", "availability": "in_stock", "stock_quantity": 12},
        headers=_m(ctx["token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["price"] == 250
    assert body["stock_quantity"] == 12
    assert body["job_id"]


def test_untracked_stock_is_preserved_not_coerced_to_zero(client: TestClient, register_org) -> None:
    """Phase 7's distinction carried through Phases 8 and 9. Breaking it
    here would undo all three: 0 reads as out-of-stock."""
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]

    body = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer",
        json={"price": 10, "currency": "EUR", "availability": "in_stock"},
        headers=_m(ctx["token"]),
    ).json()
    assert body["stock_quantity"] is None


def test_price_on_request_survives_sync(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]

    body = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer",
        json={"availability": "in_stock"}, headers=_m(ctx["token"]),
    ).json()
    assert body["price"] is None  # never 0


def test_offer_sync_is_idempotent_with_a_key(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]
    payload = {"price": 99, "currency": "EUR", "availability": "in_stock", "idempotency_key": "evt-1"}

    first = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer", json=payload, headers=_m(ctx["token"])
    ).json()
    second = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer", json=payload, headers=_m(ctx["token"])
    ).json()
    assert first["job_created"] is True
    assert second["job_created"] is False
    assert first["job_id"] == second["job_id"]


# --- ADVERSARIAL: what WooCommerce must NOT be able to do -------------------------


def test_commerce_sync_cannot_change_product_identity_or_status(
    client: TestClient, register_org
) -> None:
    """The central directional test. Extra fields are not merely ignored —
    there is no route on this surface that reaches Product at all."""
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]

    client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer",
        json={
            "price": 5, "currency": "EUR", "availability": "in_stock",
            "name": "HIJACKED", "status": "archived", "description": "x",
        },
        headers=_m(ctx["token"]),
    )
    product = client.get(f"/api/v1/products/{ctx['product']['id']}", headers=org["headers"]).json()
    assert product["name"] == "Taranjabin"
    assert product["status"] == "published"


def test_no_adapter_scope_can_verify_evidence_or_trust(client: TestClient, register_org) -> None:
    from app.models.enums import AdapterScope

    granted = {s.value for s in AdapterScope}
    for forbidden in ("evidence:verify", "trust:verify", "products:publish", "products:write"):
        assert forbidden not in granted


def test_commerce_credential_cannot_reach_evidence_endpoints(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    # Machine tokens are rejected by the human realm entirely.
    for path in ("/api/v1/evidence", "/api/v1/trust-records", "/api/v1/products"):
        assert client.get(path, headers=_m(ctx["token"])).status_code == 401


def test_commerce_write_scope_is_required(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    inst = ctx["installation"]
    read_only = client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": ["commerce:read"]}, headers=org["headers"],
    ).json()["token"]

    response = _map(client, read_only, ctx["product"]["id"], woo_id=321)
    assert response.status_code == 403


def test_cannot_map_another_orgs_product(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    ctx_a = _setup(client, org_a["headers"], slug="a")
    ctx_b = _setup(client, org_b["headers"], slug="b")

    response = _map(client, ctx_a["token"], ctx_b["product"]["id"], woo_id=42)
    assert response.status_code == 404


def test_cannot_sync_offer_on_another_orgs_mapping(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    ctx_a = _setup(client, org_a["headers"], slug="a")
    ctx_b = _setup(client, org_b["headers"], slug="b")
    mapping_b = _map(client, ctx_b["token"], ctx_b["product"]["id"]).json()["mapping"]

    response = client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping_b['id']}/offer",
        json={"price": 1, "currency": "EUR", "availability": "in_stock"},
        headers=_m(ctx_a["token"]),
    )
    assert response.status_code == 404


def test_commerce_mapping_list_is_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    ctx_a = _setup(client, org_a["headers"], slug="a")
    ctx_b = _setup(client, org_b["headers"], slug="b")
    _map(client, ctx_a["token"], ctx_a["product"]["id"], woo_id=11)
    _map(client, ctx_b["token"], ctx_b["product"]["id"], woo_id=22)

    listing = client.get("/api/v1/adapter/commerce/mappings", headers=_m(ctx_a["token"])).json()
    assert listing["total"] == 1
    assert listing["items"][0]["woo_product_id"] == 11


def test_database_rejects_cross_tenant_commerce_mapping(
    client: TestClient, register_org, db_session
) -> None:
    """SQL-level, bypassing the service entirely — the composite FK from
    ADR-037, applied at creation rather than retrofitted."""
    from app.models.commerce_mapping import CommerceMapping

    org_a, org_b = register_org(), register_org()
    ctx_a = _setup(client, org_a["headers"], slug="a")
    ctx_b = _setup(client, org_b["headers"], slug="b")

    rogue = CommerceMapping(
        organization_id=uuid.UUID(org_a["organization"]["id"]),
        site_id=uuid.UUID(ctx_a["site"]["id"]),
        product_id=uuid.UUID(ctx_b["product"]["id"]),  # B's product
        woo_product_id=1,
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Sync jobs ---------------------------------------------------------------------


def test_sync_job_is_recorded_and_visible_to_operators(client: TestClient, register_org) -> None:
    org = register_org()
    ctx = _setup(client, org["headers"])
    mapping = _map(client, ctx["token"], ctx["product"]["id"]).json()["mapping"]
    client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping['id']}/offer",
        json={"price": 7, "currency": "EUR", "availability": "in_stock"},
        headers=_m(ctx["token"]),
    )

    jobs = client.get("/api/v1/sync-jobs", headers=org["headers"]).json()
    assert jobs["total"] >= 1
    job = jobs["items"][0]
    assert job["job_type"] == "commerce_offer_sync"
    assert job["status"] == "succeeded"
    assert job["attempts"] == 1


def test_dead_letter_is_distinguishable_from_failed(client: TestClient, register_org, db_session) -> None:
    """A job that stopped retrying must be distinguishable from one that
    will retry — otherwise an operator cannot tell which need a human."""
    from app.models.enums import SyncJobType
    from app.services import commerce_sync_service

    org = register_org()
    ctx = _setup(client, org["headers"])
    job, _ = commerce_sync_service.enqueue_job(
        db_session, organization_id=uuid.UUID(org["organization"]["id"]),
        site_id=uuid.UUID(ctx["site"]["id"]), job_type=SyncJobType.COMMERCE_OFFER_SYNC,
        payload={}, idempotency_key=None, actor_user_id=None,
    )

    commerce_sync_service.mark_running(db_session, job=job)
    commerce_sync_service.mark_failed(db_session, job=job, error="boom")
    assert job.status.value == "failed"  # will retry

    for _ in range(commerce_sync_service.MAX_ATTEMPTS):
        commerce_sync_service.mark_running(db_session, job=job)
        commerce_sync_service.mark_failed(db_session, job=job, error="boom")
    assert job.status.value == "dead_letter"  # stopped trying


def test_sync_jobs_are_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    ctx_b = _setup(client, org_b["headers"], slug="b")
    mapping_b = _map(client, ctx_b["token"], ctx_b["product"]["id"]).json()["mapping"]
    client.post(
        f"/api/v1/adapter/commerce/mappings/{mapping_b['id']}/offer",
        json={"price": 3, "currency": "EUR", "availability": "in_stock"},
        headers=_m(ctx_b["token"]),
    )
    assert client.get("/api/v1/sync-jobs", headers=org_a["headers"]).json()["total"] == 0
