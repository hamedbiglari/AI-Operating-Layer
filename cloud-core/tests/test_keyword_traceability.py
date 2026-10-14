"""
REQ-KW-004 — Keyword → Research → Source → Evidence → Claim → Knowledge → Version → Published.
Every artifact is created through the real API; the first link is created by the real
"search new sources" flow (not inserted by the test).
"""
import uuid

from fastapi.testclient import TestClient


def _post(client, path, org, body, ok=(200, 201)):
    r = client.post(f"/api/v1{path}", json=body, headers=org["headers"])
    assert r.status_code in ok, f"{path}: {r.status_code} {r.text[:300]}"
    return r.json()


def _get(client, path, org, ok=200):
    r = client.get(f"/api/v1{path}", headers=org["headers"])
    assert r.status_code == ok, f"{path}: {r.status_code} {r.text[:300]}"
    return r.json()


def _ko(client, org):
    return _post(client, "/knowledge", org, {"canonical_name": f"KO {uuid.uuid4().hex[:8]}", "object_type": "ingredient"})


def _keyword(client, org, ko_id, text="example keyword"):
    _post(client, f"/knowledge/{ko_id}/keywords", org, [{"keyword": text, "type": "primary"}])
    return _get(client, f"/knowledge/{ko_id}/keywords", org)["items"][0]


def _search_sources(client, org, ko_id, kw_id):
    return _post(client, f"/knowledge/{ko_id}/keywords/search-sources", org, {"keyword_ids": [kw_id]})["tasks"][0]


def test_search_new_sources_creates_the_first_trace_link(client: TestClient, register_org) -> None:
    org = register_org(); ko = _ko(client, org); kw = _keyword(client, org, ko["id"])
    task = _search_sources(client, org, ko["id"], kw["id"])
    view = _get(client, f"/keyword-traces/keyword/{kw['id']}", org)
    assert len(view["traces"]) == 1
    t = view["traces"][0]
    assert t["research_task_id"] == task["research_task_id"] and t["stage"] == "research_task"
    # honest partial chain: not published, not complete
    assert view["is_complete"] is False and t["published_target"] is None


def test_full_keyword_to_published_content_chain(client: TestClient, register_org) -> None:
    org = register_org(); ko = _ko(client, org); kw = _keyword(client, org, ko["id"])
    task = _search_sources(client, org, ko["id"], kw["id"])
    src = _post(client, "/sources", org, {"source_type": "url", "title": "Lab report",
                "url": f"https://example.org/{uuid.uuid4().hex}", "reliability_score": 0.8})
    ev = _post(client, "/evidence", org, {"source_id": src["id"], "summary": "Mannitol detected",
               "directness": "direct", "evidence_strength": "moderate"})
    ent = _post(client, "/entities", org, {"knowledge_object_id": ko["id"], "entity_type": "ingredient", "canonical_name": "E"})
    cl = _post(client, "/claims", org, {"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
               "predicate": "contains", "object_value": "mannitol", "claim_type": "composition"})
    _post(client, "/claim-evidence", org, {"claim_id": cl["id"], "evidence_id": ev["id"], "relation": "supports"})
    # knowledge update creates a new version
    upd = client.patch(f"/api/v1/knowledge/{ko['id']}", json={"description": "Contains mannitol (lab-tested)."},
                       headers=org["headers"])
    assert upd.status_code == 200, upd.text[:200]
    version = upd.json().get("version")
    base = {"keyword_id": kw["id"], "research_task_id": task["research_task_id"]}
    _post(client, "/keyword-traces", org, {**base, "source_id": src["id"], "evidence_id": ev["id"]})
    _post(client, "/keyword-traces", org, {**base, "claim_id": cl["id"], "knowledge_object_id": ko["id"],
                                          "knowledge_version_id": version})
    target = f"https://shop.example/knowledge/{ko['id']}"
    _post(client, "/keyword-traces", org, {**base, "published_target": target})
    view = _get(client, f"/keyword-traces/keyword/{kw['id']}", org)
    t = view["traces"][0]
    assert view["is_complete"] and t["stage"] == "published"
    assert (t["source_id"], t["evidence_id"], t["claim_id"], t["knowledge_object_id"]) == \
           (src["id"], ev["id"], cl["id"], ko["id"])
    assert t["knowledge_version_id"] == version and t["published_target"] == target


def test_trace_cannot_skip_stages(client: TestClient, register_org) -> None:
    """Honesty: "published" cannot be recorded while evidence/claim are missing."""
    org = register_org(); ko = _ko(client, org); kw = _keyword(client, org, ko["id"])
    task = _search_sources(client, org, ko["id"], kw["id"])
    r = client.post("/api/v1/keyword-traces", headers=org["headers"], json={
        "keyword_id": kw["id"], "research_task_id": task["research_task_id"],
        "published_target": "https://shop.example/x"})
    assert r.status_code == 422
    assert _get(client, f"/keyword-traces/keyword/{kw['id']}", org)["is_complete"] is False


def test_trace_cannot_reference_another_tenants_artifacts(client: TestClient, register_org) -> None:
    a = register_org(); b = register_org()
    ko_a = _ko(client, a); kw_a = _keyword(client, a, ko_a["id"])
    task_a = _search_sources(client, a, ko_a["id"], kw_a["id"])
    ko_b = _ko(client, b); kw_b = _keyword(client, b, ko_b["id"])
    # B reads A's keyword trace -> 404 (not an empty list that confirms existence)
    _get(client, f"/keyword-traces/keyword/{kw_a['id']}", b, ok=404)
    # B writes a trace pointing at A's research task -> 404
    r = client.post("/api/v1/keyword-traces", headers=b["headers"],
                    json={"keyword_id": kw_b["id"], "research_task_id": task_a["research_task_id"]})
    assert r.status_code == 404
    # B writes a trace for A's keyword -> 404
    r = client.post("/api/v1/keyword-traces", headers=b["headers"], json={"keyword_id": kw_a["id"]})
    assert r.status_code == 404


def test_one_keyword_many_research_runs(client: TestClient, register_org) -> None:
    org = register_org(); ko = _ko(client, org); kw = _keyword(client, org, ko["id"])
    _search_sources(client, org, ko["id"], kw["id"]); _search_sources(client, org, ko["id"], kw["id"])
    assert len(_get(client, f"/keyword-traces/keyword/{kw['id']}", org)["traces"]) == 2
