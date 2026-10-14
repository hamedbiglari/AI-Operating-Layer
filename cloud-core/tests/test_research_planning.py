"""Research query sets (§12), evidence-completion tasks (§16), new gap types (§23), job counters (§32) — ADR-111."""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.integrations.research import scholarly
from app.services import federated_research_service as fsvc
from tests.test_federated_research import _handler, _ko

QS = "/api/v1/research/query-sets"
CT = "/api/v1/evidence-completion-tasks"


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.setattr(fsvc, "default_providers", lambda transport=None: scholarly.default_providers(httpx.MockTransport(_handler())))


# ---------------------------------------------------------------- §12 query sets
def test_a_query_set_is_saved_editable_and_re_runnable(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    r = client.post(QS, headers=org["headers"], json={"knowledge_object_id": ko["id"], "name": "Laxative evidence",
                    "description": "what we keep asking", "keyword_ids": [kw["Taranjabin"]["id"], kw["laxative"]["id"]],
                    "mode": "agent"})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["run_count"] == 0 and s["last_run_at"] is None and len(s["keyword_ids"]) == 2
    patched = client.patch(f"{QS}/{s['id']}", headers=org["headers"],
                           json={"name": "Laxative evidence (v2)", "extra_terms": ["constipation"]}).json()
    assert patched["name"] == "Laxative evidence (v2)" and patched["extra_terms"] == ["constipation"]
    run = client.post(f"{QS}/{s['id']}/run", headers=org["headers"])
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["query_set"]["run_count"] == 1 and body["query_set"]["last_run_at"]
    assert body["run"]["unique_sources"] > 0
    again = client.post(f"{QS}/{s['id']}/run", headers=org["headers"]).json()
    assert again["query_set"]["run_count"] == 2 and again["run"]["new_sources"] == 0      # comparable over time
    listed = client.get(f"{QS}?knowledge_object_id={ko['id']}", headers=org["headers"]).json()
    assert listed["total"] == 1


def test_query_set_validation_and_isolation(client: TestClient, register_org, providers) -> None:
    a, b = register_org(), register_org()
    ko, kw = _ko(client, a)
    client.post(QS, headers=a["headers"], json={"knowledge_object_id": ko["id"], "name": "Dup", "keyword_ids": []})
    dup = client.post(QS, headers=a["headers"], json={"knowledge_object_id": ko["id"], "name": "Dup", "keyword_ids": []})
    assert dup.status_code == 409
    assert client.post(QS, headers=a["headers"], json={"knowledge_object_id": ko["id"], "name": "Bad keyword",
                       "keyword_ids": [str(uuid.uuid4())]}).status_code == 404
    assert client.post(QS, headers=b["headers"], json={"knowledge_object_id": ko["id"], "name": "Other tenant",
                       "keyword_ids": []}).status_code == 404
    assert client.get(QS, headers=b["headers"]).json()["total"] == 0


# ---------------------------------------------------------------- §16 evidence completion
def _ko_and_evidence(client, org, directness="direct", route="direct_subject", verified=True):
    ko = client.post("/api/v1/knowledge", headers=org["headers"],
                     json={"canonical_name": f"KO-{uuid.uuid4().hex[:6]}", "object_type": "ingredient"}).json()
    src = client.post("/api/v1/sources", headers=org["headers"],
                      json={"title": "A trial", "source_type": "scientific_paper"}).json()
    ev = client.post("/api/v1/evidence", headers=org["headers"],
                     json={"source_id": src["id"], "summary": "A finding", "directness": directness,
                           "evidence_strength": "moderate"}).json()
    return ko, ev


def test_a_completion_task_tracks_what_is_still_missing(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko, ev = _ko_and_evidence(client, org)
    t = client.post(CT, headers=org["headers"], json={"knowledge_object_id": ko["id"],
                    "what_is_missing": "a human trial of Taranjabin itself",
                    "required_route": "direct_subject", "required_directness": "direct"})
    assert t.status_code == 201, t.text
    task = t.json()
    assert task["status"] == "open" and task["closed_at"] is None
    # it cannot be satisfied by nothing
    assert client.patch(f"{CT}/{task['id']}", headers=org["headers"], json={"status": "satisfied"}).status_code == 422
    # nor by unreviewed evidence
    assert client.patch(f"{CT}/{task['id']}", headers=org["headers"],
                        json={"status": "satisfied", "satisfied_by_evidence_id": ev["id"]}).status_code == 409
    db_session.execute(text("UPDATE evidence SET status = 'verified', evidence_route = 'direct_subject' WHERE id = :i"), {"i": ev["id"]})
    db_session.flush()
    db_session.expire_all()
    db_session.expire_all()
    db_session.expire_all()
    resp = client.patch(f"{CT}/{task['id']}", headers=org["headers"],
                        json={"status": "satisfied", "satisfied_by_evidence_id": ev["id"]})
    assert resp.status_code == 200, resp.text
    done = resp.json()
    assert done["status"] == "satisfied" and done["satisfied_by_evidence_id"] == ev["id"] and done["closed_at"]
    assert db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'evidence_completion.updated'")).scalar_one() >= 1


def test_the_wrong_kind_of_evidence_cannot_satisfy_a_task(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko, ev = _ko_and_evidence(client, org, directness="indirect")
    db_session.execute(text("UPDATE evidence SET status = 'verified', evidence_route = 'compound_human' WHERE id = :i"), {"i": ev["id"]})
    db_session.flush()
    db_session.expire_all()
    db_session.expire_all()
    db_session.expire_all()
    task = client.post(CT, headers=org["headers"], json={"knowledge_object_id": ko["id"],
                       "what_is_missing": "direct human evidence", "required_directness": "direct"}).json()
    r = client.patch(f"{CT}/{task['id']}", headers=org["headers"],
                     json={"status": "satisfied", "satisfied_by_evidence_id": ev["id"]})
    assert r.status_code == 409 and "requires direct evidence" in r.text
    route_task = client.post(CT, headers=org["headers"], json={"knowledge_object_id": ko["id"],
                             "what_is_missing": "a subject study", "required_route": "direct_subject"}).json()
    r2 = client.patch(f"{CT}/{route_task['id']}", headers=org["headers"],
                      json={"status": "satisfied", "satisfied_by_evidence_id": ev["id"]})
    assert r2.status_code == 409 and "direct subject route" in r2.text


def test_a_dead_end_needs_a_written_reason(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko, _ = _ko_and_evidence(client, org)
    task = client.post(CT, headers=org["headers"], json={"knowledge_object_id": ko["id"],
                       "what_is_missing": "a human trial"}).json()
    assert client.patch(f"{CT}/{task['id']}", headers=org["headers"], json={"status": "blocked"}).status_code == 422
    ok = client.patch(f"{CT}/{task['id']}", headers=org["headers"],
                      json={"status": "blocked", "outcome_note": "no such trial exists in the indexed literature"}).json()
    assert ok["status"] == "blocked" and ok["closed_at"]
    with pytest.raises(exc.IntegrityError, match="a_dead_end_needs_a_reason"):
        db_session.execute(text("UPDATE evidence_completion_tasks SET status = 'abandoned', outcome_note = NULL WHERE id = :i"), {"i": task["id"]})
        db_session.flush()
    db_session.rollback()
    assert client.get(f"{CT}?status=blocked", headers=org["headers"]).json()["total"] == 1


def test_completion_tasks_are_tenant_isolated(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    ko, _ = _ko_and_evidence(client, a)
    created = client.post(CT, headers=a["headers"], json={"knowledge_object_id": ko["id"], "what_is_missing": "a human trial"})
    assert created.status_code == 201, created.text
    task = created.json()
    assert client.get(CT, headers=b["headers"]).json()["total"] == 0
    assert client.patch(f"{CT}/{task['id']}", headers=b["headers"], json={"status": "searching"}).status_code == 404
    assert client.post(CT, headers=b["headers"], json={"knowledge_object_id": ko["id"], "what_is_missing": "a human trial"}).status_code == 404


# ---------------------------------------------------------------- §23 gap types
@pytest.mark.parametrize("gap_type", ["structure_gap", "retrieval_gap", "ux_gap", "commerce_gap"])
def test_the_new_gap_types_exist(client: TestClient, register_org, gap_type) -> None:
    org = register_org()
    ko = client.post("/api/v1/knowledge", headers=org["headers"],
                     json={"canonical_name": f"KO-{uuid.uuid4().hex[:6]}", "object_type": "ingredient"}).json()
    r = client.post("/api/v1/knowledge-gaps", headers=org["headers"],
                    json={"knowledge_object_id": ko["id"], "gap_type": gap_type, "description": "found by review",
                          "priority": "medium"})
    assert r.status_code in (200, 201), r.text
    assert r.json()["gap_type"] == gap_type


# ---------------------------------------------------------------- §11 named research modes
@pytest.mark.parametrize("mode", ["user_driven", "exploratory", "continuous"])
def test_a_question_records_why_it_exists(client: TestClient, register_org, providers, mode) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    r = client.post("/api/v1/research/questions", headers=org["headers"],
                    json={"knowledge_object_id": ko["id"], "subject": "Taranjabin", "outcome": "laxative", "mode": mode})
    assert r.status_code == 201 and r.json()["mode"] == mode
    proj = client.get(f"/api/v1/research/projects/{r.json()['research_project_id']}", headers=org["headers"]).json()
    assert proj["mode"] == mode


def test_a_gap_driven_search_is_recorded_as_gap_driven(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    gap = client.post("/api/v1/knowledge-gaps", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "gap_type": "evidence_gap",
                            "description": "no human clinical evidence", "priority": "high"}).json()
    r = client.post(f"/api/v1/research/knowledge-gaps/{gap['id']}/find-more", headers=org["headers"]).json()
    assert r["mode"] == "gap_driven"


def test_an_unknown_mode_is_refused(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    assert client.post("/api/v1/research/questions", headers=org["headers"],
                       json={"knowledge_object_id": ko["id"], "subject": "X", "mode": "vibes"}).status_code == 422
