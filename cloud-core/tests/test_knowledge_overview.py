"""
Integration tests for GET /knowledge/overview. Counts are checked against the
existing per-object list endpoints and against seeded rows; filters are
checked against GET /knowledge with the same parameters, since both use
knowledge_service.filtered_knowledge_objects.
"""

from fastapi.testclient import TestClient

OVERVIEW = "/api/v1/knowledge/overview"


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _ko(client: TestClient, headers: dict, name: str, object_type: str = "plant", status: str | None = None) -> dict:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": name, "object_type": object_type})
    if status == "published":
        ko = _post(client, headers, f"/api/v1/knowledge/{ko['id']}/publish", {})
    elif status == "archived":
        response = client.delete(f"/api/v1/knowledge/{ko['id']}", headers=headers)
        assert response.status_code == 200, response.text
    elif status:
        response = client.patch(f"/api/v1/knowledge/{ko['id']}", json={"status": status}, headers=headers)
        assert response.status_code == 200, response.text
    return ko


def _claim(client: TestClient, headers: dict, ko: dict, predicate: str, conflicting: bool = False) -> dict:
    subject = _post(client, headers, "/api/v1/entities", {
        "knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": ko["canonical_name"]})
    claim = _post(client, headers, "/api/v1/claims", {
        "knowledge_object_id": ko["id"], "subject_entity_id": subject["id"], "predicate": predicate, "object_value": "x"})
    if conflicting:
        _post(client, headers, f"/api/v1/claims/{claim['id']}/review",
              {"status": "disputed", "evidence_strength": "conflicting"})
    return claim


def _evidence(client: TestClient, headers: dict, source: dict, claim: dict, status: str | None = None) -> dict:
    evidence = _post(client, headers, "/api/v1/evidence", {"source_id": source["id"], "summary": "E"})
    if status:
        _post(client, headers, f"/api/v1/evidence/{evidence['id']}/review", {"status": status})
    _post(client, headers, "/api/v1/claim-evidence", {"claim_id": claim["id"], "evidence_id": evidence["id"]})
    return evidence


def _gap(client: TestClient, headers: dict, ko: dict, resolved: bool = False) -> dict:
    gap = _post(client, headers, "/api/v1/knowledge-gaps",
                {"knowledge_object_id": ko["id"], "gap_type": "evidence_gap", "description": "G"})
    if resolved:
        response = client.patch(f"/api/v1/knowledge-gaps/{gap['id']}", json={"status": "resolved"}, headers=headers)
        assert response.status_code == 200, response.text
    return gap


def _source(client: TestClient, headers: dict, title: str) -> dict:
    return _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": title})


def _overview(client: TestClient, headers: dict, query: str = "") -> dict:
    response = client.get(OVERVIEW + query, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _by_name(body: dict) -> dict:
    return {item["canonical_name"]: item for item in body["items"]}


def test_overview_requires_authentication(client: TestClient) -> None:
    assert client.get(OVERVIEW).status_code == 401


def test_counts_match_seeded_rows_and_list_endpoints(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    ko = _ko(client, headers, "Taranjabin")
    s1, s2 = _source(client, headers, "S1"), _source(client, headers, "S2")
    c1 = _claim(client, headers, ko, "contains")
    c2 = _claim(client, headers, ko, "relates_to")
    _claim(client, headers, ko, "is_source_of")            # no evidence linked
    _evidence(client, headers, s1, c1, status="pending_review")
    _evidence(client, headers, s1, c2, status="verified")
    shared = _evidence(client, headers, s2, c1, status="verified")
    _post(client, headers, "/api/v1/claim-evidence", {"claim_id": c2["id"], "evidence_id": shared["id"]})
    # Linking evidence recomputes a claim's evidence_strength, so the conflict is reviewed in last.
    _post(client, headers, f"/api/v1/claims/{c1['id']}/review", {"status": "disputed", "evidence_strength": "conflicting"})
    _gap(client, headers, ko)
    _gap(client, headers, ko, resolved=True)

    item = _by_name(_overview(client, headers))["Taranjabin"]
    # S1 backs two evidence rows and S2 one evidence row linked to two claims: 2 distinct sources.
    assert item["counts"] == {"sources": 2, "claims": 3, "claims_conflicting": 1, "evidence": 3,
                              "evidence_verified": 2, "evidence_pending_review": 1, "gaps_open": 1}
    assert item["finished"] is False

    claims_total = client.get(f"/api/v1/knowledge/{ko['id']}/claims", headers=headers).json()["total"]
    open_gaps = client.get(f"/api/v1/knowledge-gaps?knowledge_object_id={ko['id']}&status=open", headers=headers).json()["total"]
    assert (item["counts"]["claims"], item["counts"]["gaps_open"]) == (claims_total, open_gaps)
    # The object's own fields are the same as GET /knowledge/{id} returns.
    detail = client.get(f"/api/v1/knowledge/{ko['id']}", headers=headers).json()
    assert {k: item[k] for k in detail} == detail


def test_object_without_claims_or_gaps_has_zero_counts(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _ko(client, headers, "Empty")
    item = _by_name(_overview(client, headers))["Empty"]
    assert set(item["counts"].values()) == {0}


def test_default_order_is_action_needed_then_most_recent(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    src = _source(client, headers, "S")
    two_conflicts = _ko(client, headers, "Two conflicts")
    for p in ("a", "b"):
        _claim(client, headers, two_conflicts, p, conflicting=True)
    one_conflict_gap = _ko(client, headers, "One conflict, gap")
    _claim(client, headers, one_conflict_gap, "a", conflicting=True)
    _gap(client, headers, one_conflict_gap)
    one_conflict = _ko(client, headers, "One conflict")
    _claim(client, headers, one_conflict, "a", conflicting=True)
    pending_only = _ko(client, headers, "Pending only")
    _evidence(client, headers, src, _claim(client, headers, pending_only, "a"), status="pending_review")
    older_quiet, newer_quiet = _ko(client, headers, "Older quiet"), _ko(client, headers, "Newer quiet")

    names = [i["canonical_name"] for i in _overview(client, headers)["items"]]
    assert names == ["Two conflicts", "One conflict, gap", "One conflict", "Pending only", "Newer quiet", "Older quiet"]
    assert older_quiet and newer_quiet


def test_name_and_updated_sorts(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    for name in ("Thyme", "Garlic", "Saffron"):
        _ko(client, headers, name)
    by_name = [i["canonical_name"] for i in _overview(client, headers, "?sort=name")["items"]]
    assert by_name == ["Garlic", "Saffron", "Thyme"]
    by_updated = [i["canonical_name"] for i in _overview(client, headers, "?sort=updated")["items"]]
    assert by_updated == ["Saffron", "Garlic", "Thyme"]


def test_finished_objects_are_hidden_unless_requested(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _ko(client, headers, "Done", status="published")
    _ko(client, headers, "Draft, nothing to do")                      # approval is still an action
    _ko(client, headers, "In review", status="in_review")
    open_gap = _ko(client, headers, "Published, open gap", status="published")
    _gap(client, headers, open_gap)

    hidden = _overview(client, headers)
    assert hidden["finished_visible"] is False
    assert set(_by_name(hidden)) == {"Draft, nothing to do", "In review", "Published, open gap"}
    assert hidden["total"] == 3

    shown = _overview(client, headers, "?include_finished=true")
    assert shown["finished_visible"] is True and shown["total"] == 4
    finished = {name: item["finished"] for name, item in _by_name(shown).items()}
    assert finished == {"Done": True, "Draft, nothing to do": False, "In review": False, "Published, open gap": False}


def test_archived_objects_are_never_included(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _ko(client, headers, "Archived", status="archived")
    _ko(client, headers, "Active")
    for query in ("", "?include_finished=true", "?status=archived&include_finished=true"):
        assert "Archived" not in _by_name(_overview(client, headers, query))


def test_filters_match_the_knowledge_list(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    _ko(client, headers, "Saffron threads", object_type="plant")
    _ko(client, headers, "Saffron tea", object_type="product")
    _ko(client, headers, "Crocin", object_type="compound", status="in_review")
    for query in ("?search=saffron", "?object_type=product", "?status=in_review", "?search=saffron&object_type=plant"):
        listed = {i["id"] for i in client.get("/api/v1/knowledge" + query, headers=headers).json()["items"]}
        overview = {i["id"] for i in _overview(client, headers, query + "&include_finished=true")["items"]}
        assert overview == listed, query


def test_paging_is_stable_and_complete(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    for i in range(7):
        _ko(client, headers, f"Object {i}")
    pages = [_overview(client, headers, f"?limit=3&offset={off}") for off in (0, 3, 6)]
    ids = [i["id"] for p in pages for i in p["items"]]
    assert len(ids) == 7 and len(set(ids)) == 7
    assert all(p["total"] == 7 and p["limit"] == 3 for p in pages)
    assert [len(p["items"]) for p in pages] == [3, 3, 1]


def test_limit_defaults_to_50_and_is_capped_at_100(client: TestClient, register_org) -> None:
    headers = register_org()["headers"]
    assert _overview(client, headers)["limit"] == 50
    assert client.get(OVERVIEW + "?limit=100", headers=headers).status_code == 200
    assert client.get(OVERVIEW + "?limit=101", headers=headers).status_code == 422
    assert client.get(OVERVIEW + "?limit=0", headers=headers).status_code == 422
    assert client.get(OVERVIEW + "?sort=bogus", headers=headers).status_code == 422


def test_other_organization_is_never_counted(client: TestClient, register_org) -> None:
    org_a, org_b = register_org()["headers"], register_org()["headers"]
    mine = _ko(client, org_a, "Mine")
    theirs = _ko(client, org_b, "Theirs")
    _claim(client, org_b, theirs, "a", conflicting=True)
    _gap(client, org_b, theirs)
    body = _overview(client, org_a, "?include_finished=true")
    assert set(_by_name(body)) == {"Mine"} and body["total"] == 1
    assert set(_by_name(body)["Mine"]["counts"].values()) == {0} and mine
