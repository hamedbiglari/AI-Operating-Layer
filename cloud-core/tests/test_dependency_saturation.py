"""Source dependency / independent evidence count (§20) and research saturation (§22) — ADR-109."""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.integrations.research import scholarly
from app.services import federated_research_service as svc
from tests.test_federated_research import _handler, _ko

R = "/api/v1/research"


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.setattr(svc, "default_providers", lambda transport=None: scholarly.default_providers(httpx.MockTransport(_handler())))


def _question(client, org, ko, **kw):
    body = {"knowledge_object_id": ko["id"], "subject": "Taranjabin", "compounds": ["Mannitol"],
            "outcome": "laxative", "population": "human"}
    body.update(kw)
    r = client.post(f"{R}/questions", headers=org["headers"], json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _sources(client, org, qid):
    g = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()
    return [m["source_id"] for grp in g["groups"] for m in grp["members"]]


# ---------------------------------------------------------------- §20 dependency
def test_reviews_of_the_same_trial_count_once(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    qid = q["research_question_id"]
    ids = _sources(client, org, qid)
    assert len(ids) >= 3
    before = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()
    assert before["independent_evidence_count"] == before["sources"]          # nothing declared yet
    trial, review_a, review_b = ids[0], ids[1], ids[2]
    for rev in (review_a, review_b):
        r = client.post(f"{R}/sources/{rev}/dependencies", headers=org["headers"],
                        json={"depends_on_source_id": trial, "relation": "reviews", "note": "summarises the trial"})
        assert r.status_code == 201 and r.json()["created"] is True
    after = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()
    assert after["sources"] == before["sources"]
    assert after["independent_evidence_count"] == before["independent_evidence_count"] - 2
    group = next(g for g in after["groups"] if g["size"] == 3)
    assert group["root_source_id"] == trial and {m["role"] for m in group["members"]} == {"primary", "reviews"}
    assert "counted once" in after["note"]
    m = client.get(f"{R}/questions/{qid}/evidence-map", headers=org["headers"]).json()
    assert m["independent_evidence_count"] == after["independent_evidence_count"]


def test_a_citation_alone_stays_independent(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    qid = _question(client, org, ko)["research_question_id"]
    ids = _sources(client, org, qid)
    before = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()["independent_evidence_count"]
    client.post(f"{R}/sources/{ids[1]}/dependencies", headers=org["headers"],
                json={"depends_on_source_id": ids[0], "relation": "cites"})
    g = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()
    assert g["independent_evidence_count"] == before                      # citing is not depending
    assert any(e["relation"] == "cites" and e["independent"] for e in g["edges"])


def test_dependency_chains_are_transitive(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    qid = _question(client, org, ko)["research_question_id"]
    ids = _sources(client, org, qid)
    before = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()["independent_evidence_count"]
    client.post(f"{R}/sources/{ids[1]}/dependencies", headers=org["headers"], json={"depends_on_source_id": ids[0], "relation": "reviews"})
    client.post(f"{R}/sources/{ids[2]}/dependencies", headers=org["headers"], json={"depends_on_source_id": ids[1], "relation": "reanalyses"})
    g = client.get(f"{R}/questions/{qid}/dependency-graph", headers=org["headers"]).json()
    assert g["independent_evidence_count"] == before - 2 and max(x["size"] for x in g["groups"]) == 3


def test_dependency_validation_and_isolation(client: TestClient, register_org, providers, db_session) -> None:
    a, b = register_org(), register_org()
    ko, _ = _ko(client, a)
    qid = _question(client, a, ko)["research_question_id"]
    ids = _sources(client, a, qid)
    assert client.post(f"{R}/sources/{ids[0]}/dependencies", headers=a["headers"],
                       json={"depends_on_source_id": ids[0], "relation": "reviews"}).status_code == 422
    assert client.post(f"{R}/sources/{ids[0]}/dependencies", headers=a["headers"],
                       json={"depends_on_source_id": ids[1], "relation": "invented"}).status_code == 422
    assert client.post(f"{R}/sources/{ids[0]}/dependencies", headers=b["headers"],
                       json={"depends_on_source_id": ids[1], "relation": "reviews"}).status_code == 404
    assert client.get(f"{R}/questions/{qid}/dependency-graph", headers=b["headers"]).status_code == 404
    client.post(f"{R}/sources/{ids[1]}/dependencies", headers=a["headers"], json={"depends_on_source_id": ids[0], "relation": "reviews"})
    again = client.post(f"{R}/sources/{ids[1]}/dependencies", headers=a["headers"], json={"depends_on_source_id": ids[0], "relation": "reviews"})
    assert again.json()["created"] is False                                # idempotent
    with pytest.raises(exc.IntegrityError, match="no_self_dependency"):
        db_session.execute(text("INSERT INTO source_dependencies (id, organization_id, source_id, depends_on_source_id, relation, detected_by, created_at, updated_at) "
                                "VALUES (gen_random_uuid(), :o, :s, :s, 'reviews', 'user', now(), now())"),
                           {"o": str(a["organization"]["id"]), "s": ids[0]})
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------- §22 saturation
def test_saturation_reports_the_actual_reason(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    qid = _question(client, org, ko)["research_question_id"]
    s = client.get(f"{R}/questions/{qid}/saturation", headers=org["headers"]).json()
    assert s["iterations_run"] == len(s["routes_run"]) >= 4 and s["routes_not_yet_run"] == []
    assert s["saturated"] is True and s["reason"] in ("query_variants_exhausted", "low_marginal_yield", "duplicate_sources_only")
    assert "not a claim that the literature has been exhausted" in s["note"]
    assert all(r["seen"] >= r["new"] for r in s["new_sources_per_round"])


def test_repeating_the_same_search_reports_duplicates_only(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    qid = _question(client, org, ko)["research_question_id"]
    for _ in range(2):
        client.post(f"{R}/questions/{qid}/find-more", headers=org["headers"], json={"route": "direct_subject", "extra_terms": []})
    s = client.get(f"{R}/questions/{qid}/saturation", headers=org["headers"]).json()
    assert s["reason"] == "duplicate_sources_only" and s["saturated"] is True
    assert s["new_sources_per_round"][-1]["new"] == 0


def test_a_question_with_more_routes_left_is_not_saturated(client: TestClient, register_org, providers, monkeypatch) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    # stop after the first route so the rest remain un-run
    real = svc.run_query
    calls = {"n": 0}

    def once(*a, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            return {"research_query_id": "", "research_task_id": "", "query": "", "providers": [],
                    "unique_sources": 0, "new_sources": 0, "merged_duplicates": 0, "source_ids": []}
        return real(*a, **kw)
    monkeypatch.setattr(svc, "run_query", once)
    qid = _question(client, org, ko)["research_question_id"]
    s = client.get(f"{R}/questions/{qid}/saturation", headers=org["headers"]).json()
    assert s["saturated"] is False and s["reason"] == "not_saturated" and s["routes_not_yet_run"]


def test_all_providers_down_is_not_saturation(client: TestClient, register_org, monkeypatch) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    monkeypatch.setattr(svc, "default_providers",
                        lambda transport=None: scholarly.default_providers(httpx.MockTransport(
                            _handler(fail={"api.crossref.org", "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"}))))
    qid = _question(client, org, ko)["research_question_id"]
    s = client.get(f"{R}/questions/{qid}/saturation", headers=org["headers"]).json()
    assert s["saturated"] is False and s["reason"] == "provider_unavailable"


def test_a_person_can_declare_and_undeclare_saturation(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    qid = _question(client, org, ko)["research_question_id"]
    d = client.post(f"{R}/questions/{qid}/saturation", headers=org["headers"], json={"reason": "budget_reached"}).json()
    assert d["reason"] == "budget_reached" and d["saturated"] is True and d["declared_at"]
    assert client.post(f"{R}/questions/{qid}/saturation", headers=org["headers"], json={"reason": "made_up"}).status_code == 422
    back = client.post(f"{R}/questions/{qid}/saturation", headers=org["headers"], json={"reason": "not_saturated"}).json()
    assert back["declared_at"] is None
    other = register_org()
    assert client.get(f"{R}/questions/{qid}/saturation", headers=other["headers"]).status_code == 404
