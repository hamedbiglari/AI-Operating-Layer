"""Evidence kind (V5-knowledge-detail-evidence-kind; migration 0057): set on create or update, read back, filtered with
?kind=, NULL allowed (not classified yet), and counted per kind for a knowledge object in one grouped query."""
from fastapi.testclient import TestClient
from sqlalchemy import event


def _post(client: TestClient, headers: dict, path: str, body: dict) -> dict:
    r = client.post(path, json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _source(client: TestClient, headers: dict) -> dict:
    return _post(client, headers, "/api/v1/sources", {"source_type": "scientific_paper", "title": "Paper"})


def test_kind_is_set_read_and_filtered(client: TestClient, register_org) -> None:
    org = register_org()
    s = _source(client, org["headers"])
    trad = _post(client, org["headers"], "/api/v1/evidence", {"source_id": s["id"], "summary": "Used in Persian medicine.", "kind": "traditional_use"})
    none = _post(client, org["headers"], "/api/v1/evidence", {"source_id": s["id"], "summary": "Not classified yet."})
    assert trad["kind"] == "traditional_use" and none["kind"] is None
    page = client.get("/api/v1/evidence?kind=traditional_use", headers=org["headers"]).json()
    assert [x["id"] for x in page["items"]] == [trad["id"]]
    r = client.patch(f"/api/v1/evidence/{none['id']}", json={"kind": "human_clinical"}, headers=org["headers"])
    assert r.status_code == 200 and r.json()["kind"] == "human_clinical"
    assert client.get("/api/v1/evidence?kind=animal", headers=org["headers"]).json()["total"] == 0
    assert client.post("/api/v1/evidence", json={"source_id": s["id"], "summary": "x", "kind": "anecdote"}, headers=org["headers"]).status_code == 422


def _ko(client: TestClient, headers: dict, name: str) -> tuple[dict, dict]:
    ko = _post(client, headers, "/api/v1/knowledge", {"canonical_name": name, "object_type": "plant"})
    subject = _post(client, headers, "/api/v1/entities", {"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": name})
    return ko, subject


def test_a_knowledge_object_counts_its_evidence_per_kind(client: TestClient, register_org, db_engine) -> None:
    org, h = register_org(), None
    h = org["headers"]
    s = _source(client, h)
    ko, subj = _ko(client, h, "Taranjabin")
    other, osubj = _ko(client, h, "Saffron")
    c1 = _post(client, h, "/api/v1/claims", {"knowledge_object_id": ko["id"], "subject_entity_id": subj["id"], "predicate": "contains", "object_value": "mannitol"})
    c2 = _post(client, h, "/api/v1/claims", {"knowledge_object_id": ko["id"], "subject_entity_id": subj["id"], "predicate": "treats", "object_value": "constipation"})
    c3 = _post(client, h, "/api/v1/claims", {"knowledge_object_id": other["id"], "subject_entity_id": osubj["id"], "predicate": "contains", "object_value": "crocin"})

    def ev(kind, *claims):
        body = {"source_id": s["id"], "summary": "finding"} | ({"kind": kind} if kind else {})
        e = _post(client, h, "/api/v1/evidence", body)
        for c in claims:
            _post(client, h, "/api/v1/claim-evidence", {"claim_id": c["id"], "evidence_id": e["id"], "relation": "supports"})

    ev("compositional", c1, c2)        # linked to two claims of the object: counted once
    ev("traditional_use", c2)
    ev("traditional_use", c2)
    ev(None, c1)                       # not classified yet
    ev("human_clinical", c3)           # another object's evidence
    seen = []

    def count(conn, cursor, statement, *args):
        if "evidence" in statement and "GROUP BY" in statement.upper():
            seen.append(statement)

    event.listen(db_engine, "before_cursor_execute", count)
    try:
        body = client.get(f"/api/v1/knowledge/{ko['id']}/evidence-by-kind", headers=h).json()
    finally:
        event.remove(db_engine, "before_cursor_execute", count)
    assert body["by_kind"] == {"traditional_use": 2, "compositional": 1, "mechanistic": 0, "animal": 0, "human_clinical": 0,
                               "other": 0, "unclassified": 1}
    assert body["total"] == 4 and len(seen) == 1


def test_another_organizations_object_is_not_found(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    ko, _ = _ko(client, a["headers"], "Private")
    assert client.get(f"/api/v1/knowledge/{ko['id']}/evidence-by-kind", headers=b["headers"]).status_code == 404
