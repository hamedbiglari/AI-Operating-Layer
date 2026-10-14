"""
Integration + adversarial tests for the recommendation pipeline.

The adversarial ones matter most: they ask "can the engine be made to
recommend something it shouldn't?" rather than "does the happy path
work?"
"""

from fastapi.testclient import TestClient


def _product(client: TestClient, headers: dict, slug: str, publish: bool = True, **extra) -> dict:
    payload = {"name": f"Product {slug}", "slug": slug}
    payload.update(extra)
    product = client.post("/api/v1/products", json=payload, headers=headers).json()
    if publish:
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": "in_review"}, headers=headers)
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": "published"}, headers=headers)
    return product


def _offer(client: TestClient, headers: dict, product_id: str, **kw) -> dict:
    payload = {"price": 100, "currency": "EUR", "availability": "in_stock"}
    payload.update(kw)
    return client.post(f"/api/v1/products/{product_id}/offers", json=payload, headers=headers).json()


def _evidence(client: TestClient, headers: dict, verify: bool = False) -> dict:
    """`verify=False` by default: most tests here want an UNVERIFIED
    study, to prove unverified claims buy nothing. Helpers that need
    the verified path (`_verified_product_claim`) pass verify=True,
    because the two-layer invariant (ADR-032) requires the Evidence
    itself to be verified before a link can be."""
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"}, headers=headers
    ).json()
    evidence = client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": "A finding."}, headers=headers
    ).json()
    if verify:
        evidence = client.post(
            f"/api/v1/evidence/{evidence['id']}/review",
            json={"status": "verified"}, headers=headers,
        ).json()
    return evidence


def _verified_product_claim(client: TestClient, headers: dict, product_id: str, claim: str) -> None:
    ev = _evidence(client, headers, verify=True)
    link = client.post(
        f"/api/v1/products/{product_id}/evidence",
        json={"evidence_id": ev["id"], "claim": claim}, headers=headers,
    ).json()
    client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "verified"}, headers=headers,
    )


def _recommend(client: TestClient, headers: dict, **kw) -> dict:
    payload = {"response_mode": "recommend"}
    payload.update(kw)
    return client.post("/api/v1/recommendations", json=payload, headers=headers).json()


# --- Happy path -------------------------------------------------------------


def test_published_product_with_offer_is_recommended(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])

    body = _recommend(client, org["headers"])
    assert body["status"] in ("recommended", "recommended_with_caveat")
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["product_id"] == product["id"]
    assert body["policy_version"]


def test_recommendation_carries_structured_explanation(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])

    rec = _recommend(client, org["headers"])["recommendations"][0]
    reason = rec["reason"]
    for key in ("relevance", "evidence", "trust", "availability", "caveats", "policy_version"):
        assert key in reason
    # every signal carries score + state + detail together
    assert set(reason["evidence"]) == {"score", "state", "detail"}


# --- Abstention: the engine must be able to say no ---------------------------


def test_educate_mode_produces_no_recommendation(client: TestClient, register_org) -> None:
    """Section 34: do not push products when intent doesn't justify it —
    even when a perfectly good product exists."""
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])

    body = _recommend(client, org["headers"], response_mode="educate")
    assert body["status"] == "no_recommendation"
    assert body["recommendations"] == []
    assert "educate" in body["explanation"].lower()


def test_reassure_mode_produces_no_recommendation(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])

    body = _recommend(client, org["headers"], response_mode="reassure")
    assert body["status"] == "no_recommendation"


def test_no_products_produces_no_recommendation_not_an_error(client: TestClient, register_org) -> None:
    org = register_org()
    body = _recommend(client, org["headers"])
    assert body["status"] == "no_recommendation"
    assert body["recommendations"] == []


# --- Adversarial: things that must NOT become recommendations ----------------


def test_draft_product_is_rejected_with_a_named_gate(client: TestClient, register_org) -> None:
    """A high-quality unpublished product must not leak into results —
    and must be *visibly* rejected, not silently dropped."""
    org = register_org()
    product = _product(client, org["headers"], "draft-product", publish=False)
    _offer(client, org["headers"], product["id"])
    _verified_product_claim(client, org["headers"], product["id"], "Grade = A")

    body = _recommend(client, org["headers"])
    assert body["recommendations"] == []
    assert any(r["failed_gate"] == "product_not_published" for r in body["rejected"])


def test_out_of_stock_product_is_rejected_even_with_verified_evidence(
    client: TestClient, register_org
) -> None:
    """Excellent but unavailable — availability is a hard gate here,
    not a score penalty."""
    org = register_org()
    product = _product(client, org["headers"], "excellent-but-gone")
    _offer(client, org["headers"], product["id"], availability="out_of_stock")
    _verified_product_claim(client, org["headers"], product["id"], "Grade = A")
    _verified_product_claim(client, org["headers"], product["id"], "Origin = Iran")

    body = _recommend(client, org["headers"])
    assert body["recommendations"] == []
    assert any(r["failed_gate"] == "no_purchasable_offer" for r in body["rejected"])


def test_product_with_no_offer_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    _product(client, org["headers"], "no-offer")

    body = _recommend(client, org["headers"])
    assert any(r["failed_gate"] == "no_offer" for r in body["rejected"])


def test_withdrawn_consent_blocks_all_recommendations(client: TestClient, register_org) -> None:
    """A privacy hard gate: no score can overturn it."""
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])
    _verified_product_claim(client, org["headers"], product["id"], "Grade = A")

    context = client.post(
        "/api/v1/context", json={"source": "web", "consent_status": "granted"}, headers=org["headers"]
    ).json()
    client.post(f"/api/v1/context/{context['id']}/withdraw-consent", headers=org["headers"])

    body = _recommend(client, org["headers"], customer_context_id=context["id"])
    assert body["status"] == "no_recommendation"
    assert body["recommendations"] == []
    assert "consent" in body["explanation"].lower()


def test_unverified_evidence_does_not_make_a_product_confidently_recommended(
    client: TestClient, register_org
) -> None:
    """Uploading unverified claims must buy nothing."""
    org = register_org()
    product = _product(client, org["headers"], "many-unverified-claims")
    _offer(client, org["headers"], product["id"])
    for i in range(5):
        ev = _evidence(client, org["headers"])
        client.post(
            f"/api/v1/products/{product['id']}/evidence",
            json={"evidence_id": ev["id"], "claim": f"Unverified claim {i}"},
            headers=org["headers"],
        )

    rec = _recommend(client, org["headers"])["recommendations"][0]
    assert rec["evidence_state"] == "unknown"
    assert rec["status"] == "recommended_with_caveat"


def test_product_with_no_evidence_still_beats_product_with_rejected_evidence(
    client: TestClient, register_org
) -> None:
    """THE key ranking invariant: absence of evidence is not a defect,
    but rejected evidence is."""
    org = register_org()
    unknown = _product(client, org["headers"], "unknown-evidence")
    _offer(client, org["headers"], unknown["id"])

    rejected = _product(client, org["headers"], "rejected-evidence")
    _offer(client, org["headers"], rejected["id"])
    ev = _evidence(client, org["headers"])
    link = client.post(
        f"/api/v1/products/{rejected['id']}/evidence",
        json={"evidence_id": ev["id"], "claim": "Overstated claim"}, headers=org["headers"],
    ).json()
    client.post(
        f"/api/v1/product-evidence/{link['id']}/verify",
        json={"verification_status": "rejected"}, headers=org["headers"],
    )

    body = _recommend(client, org["headers"])
    by_id = {r["product_id"]: r for r in body["recommendations"]}
    assert by_id[unknown["id"]]["evidence_state"] == "unknown"
    assert by_id[rejected["id"]]["evidence_state"] == "negative"
    assert by_id[unknown["id"]]["final_score"] > by_id[rejected["id"]]["final_score"]


def test_verified_evidence_outranks_no_evidence(client: TestClient, register_org) -> None:
    org = register_org()
    plain = _product(client, org["headers"], "plain")
    _offer(client, org["headers"], plain["id"])

    evidenced = _product(client, org["headers"], "evidenced")
    _offer(client, org["headers"], evidenced["id"])
    _verified_product_claim(client, org["headers"], evidenced["id"], "Grade = A")
    _verified_product_claim(client, org["headers"], evidenced["id"], "Origin = Iran")

    body = _recommend(client, org["headers"])
    assert body["recommendations"][0]["product_id"] == evidenced["id"]


def test_results_are_deterministic_across_identical_requests(client: TestClient, register_org) -> None:
    """Reproducibility: same inputs, same ordering, every time."""
    org = register_org()
    for slug in ("a", "b", "c"):
        p = _product(client, org["headers"], slug)
        _offer(client, org["headers"], p["id"])

    first = [r["product_id"] for r in _recommend(client, org["headers"], persist=False)["recommendations"]]
    second = [r["product_id"] for r in _recommend(client, org["headers"], persist=False)["recommendations"]]
    assert first == second


def test_persist_false_writes_nothing(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])

    _recommend(client, org["headers"], persist=False)
    stored = client.get("/api/v1/recommendations", headers=org["headers"]).json()
    assert stored["total"] == 0


def test_persisted_recommendation_is_retrievable_and_explains_itself(
    client: TestClient, register_org
) -> None:
    """Reproducibility: a past decision must remain auditable."""
    org = register_org()
    product = _product(client, org["headers"], "taranjabin")
    _offer(client, org["headers"], product["id"])
    rec_id = _recommend(client, org["headers"])["recommendations"][0]["id"]

    fetched = client.get(f"/api/v1/recommendations/{rec_id}", headers=org["headers"]).json()
    assert fetched["policy_version"]
    assert fetched["reason"]["relevance"]["detail"]
    assert fetched["response_mode"] == "recommend"


def test_price_on_request_offer_is_still_recommendable(client: TestClient, register_org) -> None:
    """A NULL price must not be read as free, nor exclude the product."""
    org = register_org()
    product = _product(client, org["headers"], "quote-only")
    _offer(client, org["headers"], product["id"], price=None, currency=None)

    body = _recommend(client, org["headers"])
    assert len(body["recommendations"]) == 1
    assert "price on request" in body["recommendations"][0]["reason"]["availability"]["detail"].lower()


def test_untracked_stock_does_not_exclude_a_product(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "untracked")
    _offer(client, org["headers"], product["id"], stock_quantity=None)

    assert len(_recommend(client, org["headers"])["recommendations"]) == 1


def test_zero_stock_does_exclude_a_product(client: TestClient, register_org) -> None:
    org = register_org()
    product = _product(client, org["headers"], "zero-stock")
    _offer(client, org["headers"], product["id"], stock_quantity=0)

    body = _recommend(client, org["headers"])
    assert body["recommendations"] == []


def test_category_filter_narrows_candidates(client: TestClient, register_org) -> None:
    org = register_org()
    a = _product(client, org["headers"], "sweet", category="sweeteners")
    _offer(client, org["headers"], a["id"])
    b = _product(client, org["headers"], "herb", category="herbs")
    _offer(client, org["headers"], b["id"])

    body = _recommend(client, org["headers"], category="sweeteners")
    assert [r["product_id"] for r in body["recommendations"]] == [a["id"]]
