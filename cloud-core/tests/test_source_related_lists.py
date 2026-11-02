"""Lists a source's related claims and knowledge objects for the Source detail tabs
(V5-source-detail-tab-claims, V5-source-detail-tab-knowledge): GET /claims?source_id= and GET /knowledge?source_id=
keep what is backed by that source's evidence (through claim_evidence), within the caller's organization."""
from fastapi.testclient import TestClient


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _ko(client: TestClient, headers: dict, name: str) -> tuple[dict, dict]:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": name, "object_type": "plant"})
    subject = _post(client, headers, "/api/v1/entities", {"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": name})
    return ko, subject


def _claim(client: TestClient, headers: dict, ko: dict, subject: dict, value: str) -> dict:
    return _post(client, headers, "/api/v1/claims", {"knowledge_object_id": ko["id"], "subject_entity_id": subject["id"],
                                                      "predicate": "contains", "object_value": value})


def _backed(client: TestClient, headers: dict, claim: dict, source: dict) -> None:
    evidence = _post(client, headers, "/api/v1/evidence", {"source_id": source["id"], "summary": "A finding."})
    _post(client, headers, "/api/v1/claim-evidence", {"claim_id": claim["id"], "evidence_id": evidence["id"], "relation": "supports"})


def _setup(client: TestClient, headers: dict):
    paper = _post(client, headers, "/api/v1/sources", {"source_type": "scientific_paper", "title": "Paper"})
    other = _post(client, headers, "/api/v1/sources", {"source_type": "website", "title": "Other"})
    manna, ms = _ko(client, headers, "Taranjabin")
    saffron, ss = _ko(client, headers, "Saffron")
    thyme, ts = _ko(client, headers, "Thyme")
    c1, c2 = _claim(client, headers, manna, ms, "mannitol"), _claim(client, headers, manna, ms, "sucrose")
    c3, c4 = _claim(client, headers, saffron, ss, "crocin"), _claim(client, headers, thyme, ts, "thymol")
    _backed(client, headers, c1, paper)
    _backed(client, headers, c1, paper)          # two links from one source: the claim is listed once
    _backed(client, headers, c3, paper)
    _backed(client, headers, c4, other)
    _claim(client, headers, thyme, ts, "carvacrol")   # no evidence at all
    return paper, other, {"c1": c1, "c2": c2, "c3": c3, "c4": c4}


def test_claims_with_evidence_from_the_source(client: TestClient, register_org) -> None:
    org = register_org()
    paper, other, c = _setup(client, org["headers"])
    page = client.get(f"/api/v1/claims?source_id={paper['id']}", headers=org["headers"]).json()
    assert page["total"] == 2
    assert sorted(x["id"] for x in page["items"]) == sorted([c["c1"]["id"], c["c3"]["id"]])
    assert [x["id"] for x in client.get(f"/api/v1/claims?source_id={other['id']}", headers=org["headers"]).json()["items"]] == [c["c4"]["id"]]


def test_knowledge_objects_backed_by_the_source(client: TestClient, register_org) -> None:
    org = register_org()
    paper, other, _ = _setup(client, org["headers"])
    page = client.get(f"/api/v1/knowledge?source_id={paper['id']}", headers=org["headers"]).json()
    assert page["total"] == 2 and sorted(x["canonical_name"] for x in page["items"]) == ["Saffron", "Taranjabin"]
    assert [x["canonical_name"] for x in client.get(f"/api/v1/knowledge?source_id={other['id']}", headers=org["headers"]).json()["items"]] == ["Thyme"]


def test_another_organizations_source_lists_nothing(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    paper, _, _ = _setup(client, a["headers"])
    assert client.get(f"/api/v1/claims?source_id={paper['id']}", headers=b["headers"]).json()["total"] == 0
    assert client.get(f"/api/v1/knowledge?source_id={paper['id']}", headers=b["headers"]).json()["total"] == 0
