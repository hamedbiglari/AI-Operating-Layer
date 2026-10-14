"""Coverage Audit — six dimensions, versioning, cross-topic analysis, failure safety (ADR-115)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.services import coverage_audit_service as svc
from tests.test_knowledge_schema import _category, _topic

K = "/api/v1/knowledge"
C = "/api/v1/categories"


def _claim_with_evidence(client, org, ko, section_key, *, supported=True, directness="direct", verified=True, db=None):
    ent = client.post("/api/v1/entities", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "entity_type": "ingredient",
                            "canonical_name": f"E{uuid.uuid4().hex[:5]}"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"],
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                              "predicate": "contains", "object_value": "mannitol",
                              "claim_type": "composition", "section_key": section_key}).json()
    if not supported:
        return claim, None
    src = client.post("/api/v1/sources", headers=org["headers"],
                      json={"title": f"Study {uuid.uuid4().hex[:5]}", "source_type": "scientific_paper"}).json()
    ev = client.post("/api/v1/evidence", headers=org["headers"],
                     json={"source_id": src["id"], "summary": "A finding", "directness": directness,
                           "evidence_strength": "moderate"}).json()
    if verified and db is not None:
        db.execute(text("UPDATE evidence SET status = 'verified' WHERE id = :i"), {"i": ev["id"]})
        db.flush()
        db.expire_all()
    client.post("/api/v1/claim-evidence", headers=org["headers"],
                json={"claim_id": claim["id"], "evidence_id": ev["id"], "relation": "supports"})
    return claim, ev


# ---------------------------------------------------------------- the six dimensions
def test_an_audit_reports_six_dimensions_and_never_one_number(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    _claim_with_evidence(client, org, ko, "composition", db=db_session)
    r = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "succeeded" and a["audit_version"] == 1 and a["duration_ms"] is not None
    assert set(a["dimensions"]) == {"source", "processing", "knowledge", "evidence", "section", "publication"}
    # no single completeness figure anywhere
    assert not any(k in a["dimensions"] for k in ("completeness", "overall", "score", "percent"))
    assert a["dimensions"]["knowledge"]["claims"] == 1
    assert a["dimensions"]["evidence"]["supported_claims"] == 1
    assert a["dimensions"]["evidence"]["direct"] == 1 and a["dimensions"]["evidence"]["indirect"] == 0
    assert a["dimensions"]["section"]["sections"] == 18
    # the audit records the knowledge version it ran against, whatever the topic is on
    live = client.get(f"{K}/{ko['id']}", headers=org["headers"]).json()["version"]
    assert a["knowledge_version"] == live


def test_dimensions_move_independently(client: TestClient, register_org, db_session) -> None:
    """Every section present, almost no evidence: section coverage must not flatter evidence coverage."""
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    for key in ("composition", "safety", "dosage"):
        _claim_with_evidence(client, org, ko, key, supported=False)
    a = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    ev = a["dimensions"]["evidence"]
    assert ev["claims"] == 3 and ev["supported_claims"] == 0 and ev["percent_supported"] == 0.0
    assert a["dimensions"]["section"]["sections"] == 18          # structure is complete
    assert a["dimensions"]["knowledge"]["claims"] == 3           # knowledge exists
    assert a["dimensions"]["source"]["total"] == 0               # yet nothing supports it


def test_an_unknown_is_never_reported_as_zero(client: TestClient, register_org) -> None:
    org = register_org()
    ko = client.post(K, headers=org["headers"], json={"canonical_name": "Bare topic", "object_type": "plant"}).json()
    a = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    d = a["dimensions"]
    assert d["source"]["percent_accessible"] is None and "No sources" in d["source"]["note"]
    assert d["processing"]["percent_extracted"] is None
    assert d["evidence"]["percent_supported"] is None
    assert d["section"]["percent_documented"] is None and "unknown, not zero" in d["section"]["note"]
    assert d["publication"]["citation_coverage"] is None and "unavailable rather than zero" in d["publication"]["note"]


def test_a_closed_section_is_not_counted_as_a_failure(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    ko = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    sections = client.get(f"{K}/{ko['id']}/sections", headers=org["headers"]).json()
    for s in sections[:4]:
        client.patch(f"/api/v1/knowledge-sections/{s['id']}", headers=org["headers"],
                     json={"status": "not_applicable", "rationale": "does not apply to a manna"})
    a = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    sec = a["dimensions"]["section"]
    assert sec["closed_with_a_reason"] == 4
    assert "excluded from the denominator" in sec["note"]
    assert sec["percent_documented"] == 0.0          # of the 14 that remain answerable


# ---------------------------------------------------------------- versioning and history
def test_every_run_is_a_new_version_and_history_is_kept(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _topic(client, org, "Taranjabin")
    first = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    second = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    assert (first["audit_version"], second["audit_version"]) == (1, 2)
    hist = client.get(f"/api/v1/coverage-audits?knowledge_object_id={ko['id']}&limit=10", headers=org["headers"]).json()
    assert hist["total"] == 2
    current = client.get(f"{K}/{ko['id']}/coverage", headers=org["headers"]).json()
    assert current["state"] == "current" and current["audit"]["audit_version"] == 2


def test_a_failed_audit_never_replaces_a_good_one(client: TestClient, register_org, db_session, monkeypatch) -> None:
    org = register_org()
    ko = _topic(client, org, "Taranjabin")
    good = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    assert good["status"] == "succeeded"

    def boom(*a, **kw):
        raise RuntimeError("counting backend unavailable")
    monkeypatch.setattr(svc, "_knowledge_dimension", boom)
    failed = client.post(f"{K}/{ko['id']}/coverage/run", headers=org["headers"]).json()
    assert failed["status"] == "failed" and "counting backend unavailable" in failed["failure_reason"]
    assert failed["dimensions"] is None
    view = client.get(f"{K}/{ko['id']}/coverage", headers=org["headers"]).json()
    assert view["state"] == "stale"
    assert view["audit"]["audit_version"] == good["audit_version"]        # the good figures still stand
    assert view["failed_attempt"]["reason"].startswith("RuntimeError")
    assert "not current" in view["message"]
    with pytest.raises(exc.IntegrityError, match="a_failure_needs_a_reason"):
        db_session.execute(text("UPDATE coverage_audits SET status='failed', failure_reason=NULL WHERE id=:i"),
                           {"i": good["id"]})
        db_session.flush()
    db_session.rollback()


def test_never_run_is_said_plainly(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _topic(client, org, "Untouched")
    view = client.get(f"{K}/{ko['id']}/coverage", headers=org["headers"]).json()
    assert view["state"] == "never_run" and view["audit"] is None and "No coverage audit" in view["message"]


# ---------------------------------------------------------------- category: cross-topic, not a sum
def test_a_category_audit_is_cross_topic(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    b = _topic(client, org, "Saffron", cat["id"])
    for ko in (a, b):
        client.post(f"{K}/{ko['id']}/sections/apply-schema", headers=org["headers"])
    # one topic documents composition; the other does not
    _claim_with_evidence(client, org, a, "composition", db=db_session)
    sec = next(s for s in client.get(f"{K}/{a['id']}/sections", headers=org["headers"]).json()
               if s["section_key"] == "composition")
    client.patch(f"/api/v1/knowledge-sections/{sec['id']}", headers=org["headers"], json={"status": "documented"})
    r = client.post(f"{C}/{cat['id']}/coverage/run", headers=org["headers"]).json()
    assert r["status"] == "succeeded" and r["schema_version"] == 1
    xt = r["cross_topic"]
    comp = xt["per_section"]["composition"]
    assert comp["topics_in_category"] == 2 and comp["documented_or_verified"] == 1
    assert comp["percent_documented"] == 50.0
    assert "a sum of topic figures would hide that" in xt["note"]
    assert len(xt["weakest_sections"]) <= 5 and xt["weakest_sections"][0]["percent_documented"] == 0.0
    assert set(xt["stale_topics"]) == {a["id"], b["id"]}       # neither topic has its own audit yet
    assert r["dimensions"]["cells_expected"] == 36 and r["dimensions"]["cells_present"] == 36


def test_a_topic_audit_clears_its_stale_flag(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    client.post(f"{K}/{a['id']}/coverage/run", headers=org["headers"])
    r = client.post(f"{C}/{cat['id']}/coverage/run", headers=org["headers"]).json()
    assert r["cross_topic"]["stale_topics"] == []


def test_pending_cross_topic_evaluations_are_surfaced(client: TestClient, register_org) -> None:
    org = register_org()
    cat = _category(client, org)
    a = _topic(client, org, "Taranjabin", cat["id"])
    _topic(client, org, "Saffron", cat["id"])
    client.post(f"{C}/{cat['id']}/sections", headers=org["headers"],
                json={"key": "harvest_season", "title": "Harvest season", "discovered_from_topic_id": a["id"]})
    r = client.post(f"{C}/{cat['id']}/coverage/run", headers=org["headers"]).json()
    assert r["cross_topic"]["pending_cross_topic_evaluations"] == 1


# ---------------------------------------------------------------- isolation and permissions
def test_coverage_is_tenant_isolated(client: TestClient, register_org) -> None:
    x, y = register_org(), register_org()
    cat = _category(client, x)
    ko = _topic(client, x, "Taranjabin", cat["id"])
    client.post(f"{K}/{ko['id']}/coverage/run", headers=x["headers"])
    client.post(f"{C}/{cat['id']}/coverage/run", headers=x["headers"])
    assert client.post(f"{K}/{ko['id']}/coverage/run", headers=y["headers"]).status_code == 404
    assert client.post(f"{C}/{cat['id']}/coverage/run", headers=y["headers"]).status_code == 404
    assert client.get(f"{K}/{ko['id']}/coverage", headers=y["headers"]).json()["state"] == "never_run"
    assert client.get("/api/v1/coverage-audits", headers=y["headers"]).json()["total"] == 0


def test_running_an_audit_needs_an_editor(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _topic(client, org, "Taranjabin")
    u = client.post("/api/v1/users", headers=org["headers"],
                    json={"email": f"v{uuid.uuid4().hex[:6]}@x.example", "name": "V",
                          "password": "viewer-pass-12345", "role": "viewer"}).json()
    tok = client.post("/api/v1/auth/login", data={"username": u["email"], "password": "viewer-pass-12345"}).json()["access_token"]
    vh = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{K}/{ko['id']}/coverage", headers=vh).status_code == 200      # a viewer may read
    assert client.post(f"{K}/{ko['id']}/coverage/run", headers=vh).status_code == 403  # but not run
    assert client.get("/api/v1/coverage-audits").status_code == 401
