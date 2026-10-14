"""
Phase 11 — agent-facing AI/REST interface.

The adversarial tests are the point: **can an external AI system be given a
false impression by this API?** Three ways that could happen, each tested:

1. absence of knowledge presented as a negative finding
2. an unverified or rejected claim presented as verified
3. a numeric score escaping and being quoted back as a rating
"""

from fastapi.testclient import TestClient


def _agent(client: TestClient, headers: dict, scopes=None, slug="s") -> str:
    site = client.post(
        "/api/v1/sites", json={"name": "S", "domain": f"{slug}.example"}, headers=headers
    ).json()
    inst = client.post(
        "/api/v1/installations",
        json={"name": "Agent", "adapter_type": "mcp", "site_id": site["id"]},
        headers=headers,
    ).json()
    return client.post(
        f"/api/v1/installations/{inst['id']}/credentials",
        json={"scopes": scopes or ["ai:query", "knowledge:read"]},
        headers=headers,
    ).json()["token"]


def _m(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _ko_with_claim(client: TestClient, headers: dict, approve: bool = False) -> tuple[dict, dict]:
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
        headers=headers,
    ).json()
    entity = client.post(
        "/api/v1/entities",
        json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"},
        headers=headers,
    ).json()
    claim = client.post(
        "/api/v1/claims",
        json={"knowledge_object_id": ko["id"], "subject_entity_id": entity["id"],
              "predicate": "has_taste", "object_value": "sweet"},
        headers=headers,
    ).json()
    if approve:
        client.post(f"/api/v1/claims/{claim['id']}/review",
                    json={"status": "approved", "note": "ok"}, headers=headers)
    return ko, claim


# --- capability manifest ------------------------------------------------------


def test_capabilities_is_discoverable_without_a_credential(client: TestClient) -> None:
    """A client must be able to read the contract before holding a key."""
    response = client.get("/api/v1/ai/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert len(body["capabilities"]) >= 3
    assert body["guarantees"] and body["refusals"]


def test_capabilities_states_the_no_score_refusal(client: TestClient) -> None:
    body = client.get("/api/v1/ai/capabilities").json()
    joined = " ".join(body["refusals"]).lower()
    assert "score" in joined or "rating" in joined
    assert "write access" in joined


# --- knowledge: absence is not negative ----------------------------------------


def test_knowledge_object_with_no_claims_reports_unknown_not_empty_success(
    client: TestClient, register_org
) -> None:
    """THE central honesty test. Zero claims must read as 'not established',
    with an explicit caveat — not as a bare empty list an agent would
    present as 'nothing notable'."""
    org = register_org()
    token = _agent(client, org["headers"])
    ko = client.post(
        "/api/v1/knowledge", json={"canonical_name": "Unknown thing", "object_type": "plant"},
        headers=org["headers"],
    ).json()

    body = client.get(f"/api/v1/ai/knowledge/{ko['id']}", headers=_m(token)).json()
    assert body["claims"] == []
    assert body["coverage"]["evidence_state"] == "unknown"
    assert body["coverage"]["caveats"], "an empty result must carry an explicit caveat"
    assert "no claims" in " ".join(body["coverage"]["caveats"]).lower()


def test_unverified_claim_is_returned_but_marked_unverified(
    client: TestClient, register_org
) -> None:
    """Hiding draft claims would misrepresent the picture as more settled
    than it is; returning them unmarked would misrepresent them as facts.
    Both are avoided."""
    org = register_org()
    token = _agent(client, org["headers"])
    ko, _ = _ko_with_claim(client, org["headers"])

    body = client.get(f"/api/v1/ai/knowledge/{ko['id']}", headers=_m(token)).json()
    assert len(body["claims"]) == 1
    claim = body["claims"][0]
    assert claim["evidence_strength"] == "unverified"
    assert claim["verified_evidence_count"] == 0
    assert body["coverage"]["unverified_claim_count"] == 1
    assert body["coverage"]["evidence_state"] == "unknown"


def test_coverage_counts_are_present_on_every_response(client: TestClient, register_org) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    ko, _ = _ko_with_claim(client, org["headers"], approve=True)

    coverage = client.get(f"/api/v1/ai/knowledge/{ko['id']}", headers=_m(token)).json()["coverage"]
    for key in ("claim_count", "approved_claim_count", "disputed_claim_count",
                "unverified_claim_count", "evidence_state", "caveats"):
        assert key in coverage


def test_knowledge_response_carries_as_of_for_cache_staleness(
    client: TestClient, register_org
) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    ko, _ = _ko_with_claim(client, org["headers"])
    assert client.get(f"/api/v1/ai/knowledge/{ko['id']}", headers=_m(token)).json()["as_of"]


# --- trust: unverified must never be listed as fact -------------------------------


def _product_with_trust(client: TestClient, headers: dict, verify_evidence: bool, verify_record: bool):
    product = client.post(
        "/api/v1/products", json={"name": "Taranjabin", "slug": "t"}, headers=headers
    ).json()
    source = client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "S"}, headers=headers
    ).json()
    evidence = client.post(
        "/api/v1/evidence", json={"source_id": source["id"], "summary": "Lab report."},
        headers=headers,
    ).json()
    if verify_evidence:
        client.post(f"/api/v1/evidence/{evidence['id']}/review",
                    json={"status": "verified"}, headers=headers)
    record = client.post(
        "/api/v1/trust-records",
        json={"subject_type": "product", "subject_id": product["id"], "trust_type": "quality",
              "claim": "SECRET_UNVERIFIED_CLAIM", "evidence_id": evidence["id"]},
        headers=headers,
    ).json()
    if verify_record:
        client.post(f"/api/v1/trust-records/{record['id']}/verify",
                    json={"verification_status": "verified"}, headers=headers)
    return product


def test_unverified_trust_claim_never_appears_in_the_response_body(
    client: TestClient, register_org
) -> None:
    """The exact leak this endpoint exists to prevent: an unverified claim
    string reaching an agent that would quote it."""
    org = register_org()
    token = _agent(client, org["headers"])
    product = _product_with_trust(client, org["headers"], verify_evidence=False, verify_record=False)

    response = client.get(f"/api/v1/ai/products/{product['id']}/trust", headers=_m(token))
    assert response.status_code == 200
    assert "SECRET_UNVERIFIED_CLAIM" not in response.text
    body = response.json()
    assert body["verified_trust"] == []
    assert body["coverage"]["evidence_state"] == "unknown"


def test_trust_record_verified_over_unverified_evidence_is_not_listed(
    client: TestClient, register_org
) -> None:
    """ADR-032's two-layer rule reaching the agent interface: a record
    cannot be verified over unverified evidence, and even a legacy row in
    that state must not be surfaced."""
    org = register_org()
    token = _agent(client, org["headers"])
    product = _product_with_trust(client, org["headers"], verify_evidence=False, verify_record=True)

    body = client.get(f"/api/v1/ai/products/{product['id']}/trust", headers=_m(token)).json()
    assert body["verified_trust"] == []


def test_fully_verified_trust_is_listed(client: TestClient, register_org) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    product = _product_with_trust(client, org["headers"], verify_evidence=True, verify_record=True)

    body = client.get(f"/api/v1/ai/products/{product['id']}/trust", headers=_m(token)).json()
    assert len(body["verified_trust"]) == 1
    assert body["verified_trust"][0]["trust_type"] == "quality"
    assert body["coverage"]["evidence_state"] in ("partial", "established")


def test_no_trust_records_is_unknown_with_an_explicit_not_negative_caveat(
    client: TestClient, register_org
) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    product = client.post(
        "/api/v1/products", json={"name": "Bare", "slug": "bare"}, headers=org["headers"]
    ).json()

    body = client.get(f"/api/v1/ai/products/{product['id']}/trust", headers=_m(token)).json()
    assert body["coverage"]["evidence_state"] == "unknown"
    assert "not a negative finding" in " ".join(body["coverage"]["caveats"]).lower()


# --- ask: abstention and no score leakage --------------------------------------------


def test_researching_intent_produces_a_refusal_not_a_product_push(
    client: TestClient, register_org
) -> None:
    """§34: do not push products when intent does not justify it. A
    researching user gets EDUCATE, which declines."""
    org = register_org()
    token = _agent(client, org["headers"])

    body = client.post("/api/v1/ai/ask", json={"topic": "taranjabin", "purchase_intent": "researching"},
                       headers=_m(token)).json()
    assert body["answerable"] is False
    assert body["products"] == []
    assert body["reason"]


def test_refusal_is_http_200_not_an_error(client: TestClient, register_org) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    response = client.post("/api/v1/ai/ask", json={"purchase_intent": "none"}, headers=_m(token))
    assert response.status_code == 200


def test_ask_never_returns_a_numeric_score(client: TestClient, register_org) -> None:
    """§33: the internal score is a decision signal, not a rating. If it
    leaves the building it will be quoted as '9.2/10'."""
    org = register_org()
    token = _agent(client, org["headers"])
    product = client.post(
        "/api/v1/products", json={"name": "P", "slug": "p"}, headers=org["headers"]
    ).json()
    for s in ("in_review", "published"):
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": s}, headers=org["headers"])
    client.post(f"/api/v1/products/{product['id']}/offers",
                json={"price": 10, "currency": "EUR"}, headers=org["headers"])

    response = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token))
    text = response.text
    for forbidden in ("final_score", "relevance_score", "evidence_score", "trust_score", "availability_score"):
        assert forbidden not in text, f"{forbidden} must not leave the building"
    body = response.json()
    if body["products"]:
        assert "rank" in body["products"][0]
        assert body["products"][0]["evidence_state"]


def test_ready_intent_can_return_products_with_states_and_caveats(
    client: TestClient, register_org
) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    product = client.post(
        "/api/v1/products", json={"name": "Taranjabin", "slug": "tj"}, headers=org["headers"]
    ).json()
    for s in ("in_review", "published"):
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": s}, headers=org["headers"])
    client.post(f"/api/v1/products/{product['id']}/offers",
                json={"price": 10, "currency": "EUR"}, headers=org["headers"])

    body = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token)).json()
    assert body["answerable"] is True
    assert body["products"][0]["name"] == "Taranjabin"
    assert body["products"][0]["evidence_state"] == "unknown"
    assert body["products"][0]["caveats"], "an unevidenced product must carry caveats"


# --- security ------------------------------------------------------------------------


def test_ai_interface_requires_authentication(client: TestClient, register_org) -> None:
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])
    assert client.get(f"/api/v1/ai/knowledge/{ko['id']}").status_code == 401
    assert client.post("/api/v1/ai/ask", json={}).status_code == 401


def test_scopes_are_enforced_independently(client: TestClient, register_org) -> None:
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])
    query_only = _agent(client, org["headers"], scopes=["ai:query"], slug="q")

    assert client.get(f"/api/v1/ai/knowledge/{ko['id']}", headers=_m(query_only)).status_code == 403
    assert client.post("/api/v1/ai/ask", json={"purchase_intent": "none"},
                       headers=_m(query_only)).status_code == 200


def test_agent_cannot_read_another_orgs_knowledge(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    token_a = _agent(client, org_a["headers"], slug="a")
    ko_b, _ = _ko_with_claim(client, org_b["headers"])

    assert client.get(f"/api/v1/ai/knowledge/{ko_b['id']}", headers=_m(token_a)).status_code == 404


def test_agent_cannot_read_another_orgs_product_trust(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    token_a = _agent(client, org_a["headers"], slug="a")
    product_b = _product_with_trust(client, org_b["headers"], verify_evidence=True, verify_record=True)

    assert client.get(
        f"/api/v1/ai/products/{product_b['id']}/trust", headers=_m(token_a)
    ).status_code == 404


def test_ask_never_returns_another_orgs_products(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    token_a = _agent(client, org_a["headers"], slug="a")
    product_b = client.post(
        "/api/v1/products", json={"name": "B Product", "slug": "bp"}, headers=org_b["headers"]
    ).json()
    for s in ("in_review", "published"):
        client.post(f"/api/v1/products/{product_b['id']}/status", json={"status": s}, headers=org_b["headers"])
    client.post(f"/api/v1/products/{product_b['id']}/offers",
                json={"price": 1, "currency": "EUR"}, headers=org_b["headers"])

    body = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token_a)).json()
    assert body["products"] == []


def test_no_write_scope_exists_on_the_ai_interface(client: TestClient) -> None:
    """Structural: an external AI cannot author facts because no scope
    grants it and no route accepts it."""
    from app.models.enums import AdapterScope

    granted = {s.value for s in AdapterScope}
    for forbidden in ("ai:write", "knowledge:write", "evidence:write", "trust:write"):
        assert forbidden not in granted


def test_ai_routes_are_read_only_except_ask(client: TestClient) -> None:
    from app.main import app

    writes = [
        (sorted(r.methods), r.path) for r in app.routes
        # "/api/v1/ai/" — the machine-facing AI interface. The trailing slash was
        # missing, so the merchant-side admin APIs /ai-executions and /ai-center
        # (added later, authenticated user APIs) were caught by accident.
        if hasattr(r, "path") and r.path.startswith("/api/v1/ai/")
        and getattr(r, "methods", set()) & {"PUT", "PATCH", "DELETE"}
    ]
    assert writes == [], f"the AI interface must expose no mutating verbs: {writes}"


# --- merchant purchase destination (project-closure correction, Phase 11 owner) ----


def _ready_product(client, headers, slug, offer_url=None):
    product = client.post("/api/v1/products", json={"name": f"P-{slug}", "slug": slug}, headers=headers).json()
    for s in ("in_review", "published"):
        client.post(f"/api/v1/products/{product['id']}/status", json={"status": s}, headers=headers)
    body = {"price": 10, "currency": "EUR"}
    if offer_url:
        body["url"] = offer_url
    client.post(f"/api/v1/products/{product['id']}/offers", json=body, headers=headers)
    return product


def test_ask_returns_the_merchant_url_from_the_offer(client: TestClient, register_org) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    _ready_product(client, org["headers"], "u1", offer_url="https://shop.example/p/u1")
    body = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token)).json()
    assert body["products"][0]["merchant_url"] == "https://shop.example/p/u1"


def test_ask_falls_back_to_the_adapter_published_permalink(client: TestClient, register_org) -> None:
    org = register_org()
    product = _ready_product(client, org["headers"], "u2")
    wp_token = _agent(client, org["headers"], scopes=["mappings:write", "ai:query"], slug="wp2")
    r = client.post("/api/v1/adapter/mappings", headers=_m(wp_token), json={
        "object_type": "product", "object_id": product["id"], "wordpress_post_id": 11,
        "wordpress_post_type": "product", "wordpress_url": "https://shop.example/?product=u2"})
    assert r.status_code in (200, 201), r.text
    body = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(wp_token)).json()
    assert body["products"][0]["merchant_url"] == "https://shop.example/?product=u2"


def test_ask_never_guesses_a_merchant_url(client: TestClient, register_org) -> None:
    org = register_org()
    token = _agent(client, org["headers"])
    _ready_product(client, org["headers"], "u3")
    body = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token)).json()
    assert body["products"][0]["merchant_url"] is None


def test_merchant_url_never_crosses_tenants(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    pa = _ready_product(client, a["headers"], "u4")
    wp_a = _agent(client, a["headers"], scopes=["mappings:write"], slug="wpa")
    client.post("/api/v1/adapter/mappings", headers=_m(wp_a), json={
        "object_type": "product", "object_id": pa["id"], "wordpress_post_id": 1,
        "wordpress_post_type": "product", "wordpress_url": "https://a.example/secret-page"})
    _ready_product(client, b["headers"], "u4")
    token_b = _agent(client, b["headers"], slug="agb")
    text = client.post("/api/v1/ai/ask", json={"purchase_intent": "ready"}, headers=_m(token_b)).text
    assert "a.example" not in text
