"""Category schema, sections and the Master Topic Matrix (ADR-114)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

C = "/api/v1/categories"
K = "/api/v1/knowledge"


def _category(client, org, name=None, starter="medicinal_plant"):
    r = client.post(C, headers=org["headers"], json={"name": name or f"Medicinal plants {uuid.uuid4().hex[:5]}",
                    "description": "Plants used medicinally", "starter": starter})
    assert r.status_code == 201, r.text
    return r.json()


def _topic(client, org, name, category_id=None):
    ko = client.post(K, headers=org["headers"],
                     json={"canonical_name": name, "object_type": "plant"}).json()
    if category_id:
        r = client.patch(f"{K}/{ko['id']}", headers=org["headers"], json={"category_id": category_id})
        assert r.status_code == 200, r.text
        ko = r.json()
    return ko


# ---------------------------------------------------------------- categories and schema
def test_a_category_comes_with_a_starting_schema(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    assert cat["schema_version"] == 1 and cat["slug"]
    defs = client.get(f"{C}/{cat['id']}/sections", headers=org["headers"]).json()
    keys = [d["key"] for d in defs]
    assert len(defs) == 18 and keys[0] == "identity" and "clinical_evidence" in keys and "adulteration" in keys
    assert [d["position"] for d in defs] == sorted(d["position"] for d in defs)
    assert all(d["origin"] == "category_schema" for d in defs)
    device = _category(client, org, name="Smartphones", starter="device")
    device_keys = [d["key"] for d in client.get(f"{C}/{device['id']}/sections", headers=org["headers"]).json()]
    assert "camera" in device_keys and "adulteration" not in device_keys     # the schema is per category


def test_object_type_is_untouched_and_a_topic_without_a_category_still_works(client: TestClient, register_org) -> None:
    org = register_org()
    ko = client.post(K, headers=org["headers"], json={"canonical_name": "Loose topic", "object_type": "ingredient"}).json()
    assert ko["object_type"] == "ingredient"
    assert client.get(f"{K}/{ko['id']}", headers=org["headers"]).status_code == 200
    assert client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json() == []
    r = client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    assert r.status_code == 409 and "no category" in r.text


def test_applying_the_schema_creates_one_cell_per_section(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    r = client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"]).json()
    assert r["sections_in_schema"] == 18 and r["created"] == 18
    again = client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"]).json()
    assert again["created"] == 0 and again["total"] == 18          # never overwrites what is there
    sections = client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()
    assert all(s["status"] == "needs_research" for s in sections)
    assert all(s["claims"] == 0 and s["evidence"] == 0 for s in sections)


# ---------------------------------------------------------------- the matrix
def test_the_matrix_is_live_data(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    b = _topic(client, org, "Saffron", cat["id"])
    for ko in (a, b):
        client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    m = client.get(f"{C}/{cat['id']}/matrix", headers=org["headers"]).json()
    assert [t["name"] for t in m["topics"]] == ["Saffron", "Taranjabin"]
    assert m["sections"] == 18 and len(m["rows"]) == 18
    row = next(r for r in m["rows"] if r["section_key"] == "clinical_evidence")
    assert len(row["cells"]) == 2 and all(c["status"] == "needs_research" for c in row["cells"])
    assert "not that the section does not apply" in m["note"]
    # a topic that has not had the schema applied shows an honest empty cell
    c = _topic(client, org, "Thyme", cat["id"])
    m2 = client.get(f"{C}/{cat['id']}/matrix", headers=org["headers"]).json()
    cell = next(x for x in m2["rows"][0]["cells"] if x["knowledge_object_id"] == c["id"])
    assert cell["exists"] is False and cell["status"] is None and "not yet" in cell["label"]


def test_status_is_derived_from_the_knowledge_base(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    ent = client.post("/api/v1/entities", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "entity_type": "ingredient", "canonical_name": "Taranjabin"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"],
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                              "predicate": "contains", "object_value": "mannitol", "claim_type": "composition",
                              "section_key": "composition"})
    assert claim.status_code in (200, 201), claim.text
    out = client.post(f"{K}/{ko['id']}/sections/recalculate", headers=org["headers"]).json()
    sections = {s["section_key"]: s for s in client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()}
    comp = sections["composition"]
    assert comp["claims"] == 1 and comp["evidence"] == 0 and comp["status"] == "partial"   # a claim with no evidence
    assert sections["safety"]["status"] == "needs_research" and sections["safety"]["claims"] == 0
    assert out["by_status"]["needs_research"] == 17 and out["by_status"]["partial"] == 1
    assert comp["last_audited_at"]


def test_a_closed_cell_needs_a_written_reason(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    s = next(x for x in client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()
             if x["section_key"] == "adulteration")
    bad = client.patch(f"/api/v1/knowledge-sections/{s['id']}", headers=org["headers"], json={"status": "not_applicable"})
    assert bad.status_code == 422 and "written reason" in bad.text
    ok = client.patch(f"/api/v1/knowledge-sections/{s['id']}", headers=org["headers"],
                      json={"status": "not_applicable", "rationale": "sold only as whole manna, adulteration does not arise"}).json()
    assert ok["status"] == "not_applicable" and ok["rationale"]
    assert client.patch(f"/api/v1/knowledge-sections/{s['id']}", headers=org["headers"],
                        json={"status": "error", "rationale": "x"}).status_code == 422   # only the system sets error
    with pytest.raises(exc.IntegrityError, match="a_closed_cell_needs_a_reason"):
        db_session.execute(text("UPDATE knowledge_sections SET status='no_evidence_found', rationale=NULL WHERE id=:i"), {"i": s["id"]})
        db_session.flush()
    db_session.rollback()


def test_a_person_s_decision_is_not_overwritten_by_a_recalculation(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    s = next(x for x in client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()
             if x["section_key"] == "dosage")
    client.patch(f"/api/v1/knowledge-sections/{s['id']}", headers=org["headers"],
                 json={"status": "experiment_required", "rationale": "needs our own measurement"})
    client.post(f"{K}/{ko['id']}/sections/recalculate", headers=org["headers"])
    after = next(x for x in client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()
                 if x["section_key"] == "dosage")
    assert after["status"] == "experiment_required"


# ---------------------------------------------------------------- cross-topic propagation
def test_a_discovered_section_is_proposed_to_siblings_not_copied(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    b = _topic(client, org, "Saffron", cat["id"])
    c = _topic(client, org, "Thyme", cat["id"])
    for ko in (a, b, c):
        client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    before = cat["schema_version"]
    sd = client.post(f"{C}/{cat['id']}/sections", headers=org["headers"],
                     json={"key": "harvest_season", "title": "Harvest season",
                           "discovered_from_topic_id": a["id"]}).json()
    assert sd["origin"] == "discovered" and sd["schema_version"] == before + 1
    props = client.get("/api/v1/section-propagations?state=pending&limit=50", headers=org["headers"]).json()
    assert props["total"] == 2                      # the two siblings, not the topic it came from
    assert {p["knowledge_object_id"] for p in props["items"]} == {b["id"], c["id"]}
    # nothing was written into the siblings' knowledge
    for ko in (b, c):
        keys = [s["section_key"] for s in client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()]
        assert "harvest_season" not in keys
    m = client.get(f"{C}/{cat['id']}/matrix", headers=org["headers"]).json()
    assert m["pending_cross_topic_evaluations"] == 2


def test_deciding_a_proposal(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    b = _topic(client, org, "Saffron", cat["id"])
    c = _topic(client, org, "Thyme", cat["id"])
    client.post(f"{C}/{cat['id']}/sections", headers=org["headers"],
                json={"key": "harvest_season", "title": "Harvest season", "discovered_from_topic_id": a["id"]})
    props = client.get("/api/v1/section-propagations?state=pending&limit=50", headers=org["headers"]).json()["items"]
    for_b = next(p for p in props if p["knowledge_object_id"] == b["id"])
    for_c = next(p for p in props if p["knowledge_object_id"] == c["id"])
    r = client.patch(f"/api/v1/section-propagations/{for_b['id']}", headers=org["headers"],
                     json={"state": "evaluated", "resulting_status": "needs_research"}).json()
    assert r["state"] == "evaluated"
    keys_b = [s["section_key"] for s in client.get(f"{K}/{b['id']}/sections", headers=org["headers"]).json()]
    assert "harvest_season" in keys_b
    assert client.patch(f"/api/v1/section-propagations/{for_c['id']}", headers=org["headers"],
                        json={"state": "skipped"}).status_code == 422              # skipping needs a reason
    skipped = client.patch(f"/api/v1/section-propagations/{for_c['id']}", headers=org["headers"],
                           json={"state": "skipped", "note": "thyme is a leaf herb, harvest season is already in distribution"}).json()
    assert skipped["state"] == "skipped" and skipped["note"]
    keys_c = [s["section_key"] for s in client.get(f"{K}/{c['id']}/sections", headers=org["headers"]).json()]
    assert "harvest_season" not in keys_c
    assert client.patch(f"/api/v1/section-propagations/{for_b['id']}", headers=org["headers"],
                        json={"state": "evaluated", "resulting_status": "not_applicable"}).status_code == 422


def test_a_section_outside_the_schema_stays_visible(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    b = _topic(client, org, "Saffron", cat["id"])
    client.post(f"{K}/{a['id']}/sections/apply-schema", headers=org["headers"])
    client.post(f"{C}/{cat['id']}/sections", headers=org["headers"],
                json={"key": "harvest_season", "title": "Harvest season", "discovered_from_topic_id": a["id"]})
    prop = client.get("/api/v1/section-propagations?state=pending", headers=org["headers"]).json()["items"][0]
    client.patch(f"/api/v1/section-propagations/{prop['id']}", headers=org["headers"],
                 json={"state": "evaluated", "resulting_status": "needs_research"})
    m = client.get(f"{C}/{cat['id']}/matrix", headers=org["headers"]).json()
    assert any(r["section_key"] == "harvest_season" for r in m["rows"])


# ---------------------------------------------------------------- isolation and validation
def test_categories_and_sections_are_tenant_isolated(client: TestClient, register_org) -> None:
    x, y = register_org(), register_org()
    cat = _category(client, x)
    ko = _topic(client, x, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=x["headers"])
    assert client.get(C, headers=y["headers"]).json()["total"] == 0
    assert client.get(f"{C}/{cat['id']}", headers=y["headers"]).status_code == 404
    assert client.get(f"{C}/{cat['id']}/matrix", headers=y["headers"]).status_code == 404
    assert client.get(f"{C}/{cat['id']}/sections", headers=y["headers"]).status_code == 404
    assert client.get(f"{K}/{ko['id']}/sections", headers=y["headers"]).json() == []
    assert client.get("/api/v1/section-propagations", headers=y["headers"]).json()["total"] == 0


def test_validation(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    dup = client.post(C, headers=org["headers"], json={"name": cat["name"]})
    assert dup.status_code == 409
    assert client.post(C, headers=org["headers"], json={"name": "X", "starter": "nope"}).status_code == 422
    assert client.post(f"{C}/{cat['id']}/sections", headers=org["headers"],
                       json={"key": "identity", "title": "Identity again"}).status_code == 409
    assert client.post(f"{C}/{uuid.uuid4()}/sections", headers=org["headers"],
                       json={"key": "x_section", "title": "Extra"}).status_code == 404
