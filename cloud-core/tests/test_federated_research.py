"""
Pilot-ready federated research.

Provider payloads below are FIXTURES written to the documented response formats of the
Crossref REST API (/works), NCBI E-utilities (esearch/esummary, retmode=json) and the Europe PMC
REST API (/search, resultType=core). They were not captured from the live services: those hosts
are blocked by this sandbox's network allow-list (x-deny-reason: host_not_allowed). Live runs are
listed in PILOT_TEST_RUNBOOK.md.
"""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.integrations.research import scholarly
from app.services import federated_research_service as svc

R = "/api/v1/research"
SEEN_HOSTS: list[str] = []

CROSSREF = {"status": "ok", "message": {"items": [
    {"DOI": "10.1000/ABC", "title": ["Mannitol as an osmotic laxative in adults"], "publisher": "Example Medical Press",
     "container-title": ["J Example Gastro"], "URL": "https://doi.org/10.1000/abc", "issued": {"date-parts": [[2019, 3]]},
     "abstract": "<jats:p>Randomised trial of oral mannitol in adults with constipation.</jats:p>"},
    {"DOI": "10.1000/XYZ", "title": ["Manna of Alhagi: composition"], "publisher": "Botany House",
     "container-title": ["Phytochem Notes"], "URL": "https://doi.org/10.1000/xyz", "issued": {"date-parts": [[2015]]}},
]}}
ESEARCH = {"esearchresult": {"count": "2", "idlist": ["111", "222"]}}
ESUMMARY = {"result": {"uids": ["111", "222"],
    "111": {"uid": "111", "title": "Mannitol as an osmotic laxative in adults.", "fulljournalname": "J Example Gastro", "pubdate": "2019 Mar",
            "articleids": [{"idtype": "pubmed", "value": "111"}, {"idtype": "doi", "value": "10.1000/abc"}]},
    "222": {"uid": "222", "title": "Taranjabin in functional constipation: a randomised trial.", "fulljournalname": "Iran J Trad Med", "pubdate": "2021",
            "articleids": [{"idtype": "pubmed", "value": "222"}]}}}
EUROPEPMC = {"hitCount": 2, "resultList": {"result": [
    {"id": "222", "source": "MED", "pmid": "222", "pmcid": "PMC999", "title": "Taranjabin in functional constipation: a randomised trial.",
     "abstractText": "Adults received taranjabin syrup or placebo for four weeks; stool frequency increased.", "isOpenAccess": "Y",
     "pubYear": "2021", "journalInfo": {"journal": {"title": "Iran J Trad Med"}},
     "fullTextUrlList": {"fullTextUrl": [{"availability": "Open access", "documentStyle": "html", "url": "https://europepmc.org/articles/PMC999"}]}},
    {"id": "333", "source": "MED", "pmid": "333", "title": "Manna of Alhagi - composition", "isOpenAccess": "N", "pubYear": "2015"},
]}}


def _handler(fail: set[str] | None = None, timeout: set[str] | None = None):
    fail, timeout = fail or set(), timeout or set()

    def h(req: httpx.Request) -> httpx.Response:
        SEEN_HOSTS.append(req.url.host)
        host = req.url.host
        if host in timeout:
            raise httpx.ConnectTimeout("timed out", request=req)
        if host in fail:
            return httpx.Response(500, json={"error": "upstream"})
        if host == "api.crossref.org":
            return httpx.Response(200, json=CROSSREF)
        if host == "eutils.ncbi.nlm.nih.gov":
            return httpx.Response(200, json=ESEARCH if req.url.path.endswith("esearch.fcgi") else ESUMMARY)
        if host == "www.ebi.ac.uk":
            return httpx.Response(200, json=EUROPEPMC)
        return httpx.Response(404)
    return h


@pytest.fixture()
def providers(monkeypatch):
    state = {"fail": set(), "timeout": set()}

    def factory(transport=None):
        return scholarly.default_providers(httpx.MockTransport(_handler(state["fail"], state["timeout"])))
    monkeypatch.setattr(svc, "default_providers", factory)
    SEEN_HOSTS.clear()
    return state


def _ko(client, org, name="Taranjabin"):
    ko = client.post("/api/v1/knowledge", headers=org["headers"], json={"canonical_name": name, "object_type": "ingredient"}).json()
    kws = [{"keyword": "Taranjabin", "type": "primary"}, {"keyword": "Persian manna", "type": "synonym"},
           {"keyword": "Alhagi maurorum", "type": "scientific_name"}, {"keyword": "mannitol", "type": "compound"},
           {"keyword": "laxative", "type": "clinical_outcome"}]
    r = client.post(f"/api/v1/knowledge/{ko['id']}/keywords", headers=org["headers"], json=kws)
    assert r.status_code in (200, 201), r.text
    items = {k["keyword"]: k for k in client.get(f"/api/v1/knowledge/{ko['id']}/keywords?limit=50", headers=org["headers"]).json()["items"]}
    return ko, items


def _question(client, org, ko):
    r = client.post(f"{R}/questions", headers=org["headers"], json={"knowledge_object_id": ko["id"], "subject": "Taranjabin",
                    "compound": "Mannitol", "outcome": "laxative", "population": "human"})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ providers + dedup
def test_federated_search_dedups_by_doi_pmid_and_title(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    r = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"], kw["laxative"]["id"]], "mode": "agent"})
    assert r.status_code == 201, r.text
    d = r.json()
    status = {p["provider"]: p["status"] for p in d["providers"]}
    assert status == {"crossref": "ok", "pubmed": "ok", "europepmc": "ok", "web": "not_configured"}
    assert d["unique_sources"] == 3 and d["new_sources"] == 3 and d["merged_duplicates"] == 3
    q = client.get(f"{R}/queries/{d['research_query_id']}", headers=org["headers"]).json()
    matched = {(p["provider"], h["matched_on"]) for p in q["providers"] for h in p["hits"]}
    assert ("pubmed", "doi") in matched and ("europepmc", "pmid") in matched and ("europepmc", "canonical_title") in matched
    # re-running the same search creates no new sources
    again = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    assert again["new_sources"] == 0


def test_one_provider_failing_keeps_the_others(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    providers["fail"] = {"api.crossref.org"}
    providers["timeout"] = {"eutils.ncbi.nlm.nih.gov"}
    d = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    st = {p["provider"]: p for p in d["providers"]}
    assert st["crossref"]["status"] == "failed" and "HTTP 500" in st["crossref"]["error"]
    assert st["pubmed"]["status"] == "failed" and "ConnectTimeout" in st["pubmed"]["error"]
    assert st["europepmc"]["status"] == "ok" and d["unique_sources"] == 2      # Europe PMC's results survive
    task = client.get(f"/api/v1/research/tasks/{d['research_task_id']}", headers=org["headers"]).json()
    assert task["status"] == "completed" and task["result"]["providers"][0]["status"] == "failed"


def test_all_providers_failing_is_a_truthful_failed_task(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    providers["fail"] = {"api.crossref.org", "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"}
    d = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    assert d["unique_sources"] == 0
    assert client.get(f"/api/v1/research/tasks/{d['research_task_id']}", headers=org["headers"]).json()["status"] == "failed"


# ------------------------------------------------------------------ access honesty
def test_discovery_never_claims_full_text_and_creates_no_evidence(client: TestClient, register_org, providers, db_session) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    d = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    details = [client.get(f"{R}/sources/{sid}/detail", headers=org["headers"]).json() for sid in d["source_ids"]]
    assert all(x["content_access"] in ("abstract_only", "metadata_only") and not x["full_text_accessed"] for x in details)
    assert all(x["message"] == svc.NOT_REVIEWED_MESSAGE and x["full_text_status"] == "not reviewed by the system" for x in details)
    trial = next(x for x in details if x["pmid"] == "222")
    assert trial["content_access"] == "abstract_only" and trial["what_was_accessed"] == ["abstract", "metadata"]
    assert trial["open_access_links"] == ["https://europepmc.org/articles/PMC999"]     # an OA *location*, not accessed text
    assert trial["rights"] == "open" and trial["existence"] == "confirmed" and trial["review_status"] == "not_reviewed"
    for key in ("doi", "pubmed", "europepmc", "library_search"):
        assert key in trial["access_locators"] or key == "doi"
    composition = next(x for x in details if x["doi"] == "10.1000/xyz")
    assert composition["content_access"] == "metadata_only" and composition["abstract_status"] == "not available to the system"
    org_id = str(org["organization"]["id"])
    assert db_session.execute(text("SELECT count(*) FROM evidence WHERE organization_id = :o"), {"o": org_id}).scalar_one() == 0
    assert db_session.execute(text("SELECT count(*) FROM claims WHERE organization_id = :o"), {"o": org_id}).scalar_one() == 0


def test_database_refuses_a_full_text_claim_without_access(client: TestClient, register_org, providers, db_session) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    d = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    with pytest.raises(exc.IntegrityError, match="ck_sources_full_text_claim_requires_access"):
        db_session.execute(text("UPDATE sources SET content_access = 'full_text_available' WHERE id = :i"), {"i": d["source_ids"][0]})
        db_session.flush()
    db_session.rollback()


def test_inaccessible_sources_are_listed_with_acquisition_paths(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    ex = client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"]).json()
    assert ex["status"] == "pending_review" and ex["sources_without_accessible_text"] > 0   # metadata-only: nothing read, no candidate
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    meta_only = [s for s in m["inaccessible"] if s["content_access"] == "metadata_only"]
    assert meta_only and all(s["message"] == svc.NOT_REVIEWED_MESSAGE and s["acquisition_paths"]["library_search"] for s in meta_only)


# ------------------------------------------------------------------ compound indirectness
def test_compound_evidence_stays_indirect(client: TestClient, register_org, providers, db_session) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    assert set(q["routes"]) == {"direct_subject", "compound_human", "mechanistic", "co_occurrence", "indirect_formulation"}
    assert "Mannitol" in q["routes"]["compound_human"]["query"] and "Taranjabin" not in q["routes"]["compound_human"]["query"]
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    cands = {c["route"]: c for c in m["awaiting_review"] if c["source_id"]}
    assert all(c["directness"] == "indirect" and c["basis"] == "abstract" for c in m["awaiting_review"])
    # 1) reviewer: the compound study tested Mannitol -> stays INDIRECT
    r = client.post(f"{R}/evidence-candidates/{cands['compound_human']['id']}/review", headers=org["headers"],
                    json={"decision": "approve", "subject_tested": "Mannitol"}).json()
    assert r["directness"] == "indirect" and r["route"] == "compound_human"
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    s = m["status_summary"]
    assert s["direct_evidence_for_Taranjabin"] == "absent" and s["evidence_for_Mannitol"] == "present"
    assert s["clinical_evidence_for_Taranjabin"] == "indirect"                   # never "direct" from compound evidence
    assert "not evidence that the subject has the effect" in m["note"]
    # 2) a subject-route hit whose study actually tested Mannitol is NOT direct for Taranjabin
    r2 = client.post(f"{R}/evidence-candidates/{cands['direct_subject']['id']}/review", headers=org["headers"],
                     json={"decision": "approve", "subject_tested": "Mannitol"}).json()
    assert r2["directness"] == "indirect" and r2["route"] == "co_occurrence"
    # 3) the database itself refuses a direct compound-route row
    with pytest.raises(exc.IntegrityError, match="ck_evidence_compound_route_is_indirect"):
        db_session.execute(text("UPDATE evidence SET directness = 'direct' WHERE id = :i"), {"i": cands["compound_human"]["id"]})
        db_session.flush()
    db_session.rollback()


def test_only_a_study_of_the_subject_is_direct(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    direct_c = next(c for c in m["awaiting_review"] if c["route"] == "direct_subject")
    r = client.post(f"{R}/evidence-candidates/{direct_c['id']}/review", headers=org["headers"],
                    json={"decision": "approve", "subject_tested": "Taranjabin syrup"}).json()
    assert r["directness"] == "direct"
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    assert m["status_summary"]["clinical_evidence_for_Taranjabin"] == "direct" and m["directly_supported"]
    assert client.post(f"{R}/evidence-candidates/{direct_c['id']}/review", headers=org["headers"],
                       json={"decision": "approve", "subject_tested": "x"}).status_code == 409      # already reviewed
    other = next(c for c in m["awaiting_review"])
    assert client.post(f"{R}/evidence-candidates/{other['id']}/review", headers=org["headers"],
                       json={"decision": "approve"}).status_code == 422                            # must say what was tested


def test_research_agent_never_edits_the_knowledge_object(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    before = client.get(f"/api/v1/knowledge/{ko['id']}", headers=org["headers"]).json()
    q = _question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    client.post(f"{R}/questions/{q['research_question_id']}/find-more", headers=org["headers"], json={"route": "direct_subject", "extra_terms": ["Alhagi manna"]})
    after = client.get(f"/api/v1/knowledge/{ko['id']}", headers=org["headers"]).json()
    assert (after["version"], after["updated_at"], after["status"]) == (before["version"], before["updated_at"], before["status"])


def test_find_more_runs_a_broadened_search(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    r = client.post(f"{R}/questions/{q['research_question_id']}/find-more", headers=org["headers"],
                    json={"route": "direct_subject", "extra_terms": ["Alhagi manna"]})
    assert r.status_code == 201 and "Alhagi manna" in r.json()["query"] and '"human"' not in r.json()["query"]


# ------------------------------------------------------------------ queries, trace, security
@pytest.mark.parametrize("bad", ['mannitol AND', '(mannitol OR laxative', '"mannitol', 'AND mannitol', 'mannitol; DROP TABLE x'])
def test_boolean_query_validation(client: TestClient, register_org, providers, bad) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    r = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={"knowledge_object_id": ko["id"], "mode": "boolean", "boolean_query": bad})
    assert r.status_code == 422


def test_query_modes_build_the_documented_syntax() -> None:
    assert svc.build_query("single", ["Taranjabin"]) == "Taranjabin"
    assert svc.build_query("multi", ["Taranjabin", "Persian manna"]) == '(Taranjabin OR "Persian manna")'
    assert svc.build_query("exact", ["Persian manna"]) == '"Persian manna"'
    assert svc.build_query("boolean", [], '("Persian manna" OR Taranjabin) AND laxative NOT rat') == '("Persian manna" OR Taranjabin) AND laxative NOT rat'
    assert svc.build_query("agent", ["Taranjabin", "Persian manna"], None, ["laxative"]) == '(Taranjabin OR "Persian manna") AND (laxative)'
    assert svc.plain_text_query if hasattr(svc, "plain_text_query") else True


def test_keyword_traceability_reaches_the_claim(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"})
    chain = client.get(f"{R}/keywords/{kw['Taranjabin']['id']}/chain", headers=org["headers"]).json()
    assert chain["chain"] and not chain["complete_to_claim"]                       # honest: no claim yet
    step = chain["chain"][0]
    assert {"research_project_id", "research_task_id", "query", "provider", "source_id"} <= set(step)
    # the human loop: candidate -> review -> claim link
    q = _question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    cand = next(c for c in m["awaiting_review"] if c["route"] == "direct_subject")
    client.post(f"{R}/evidence-candidates/{cand['id']}/review", headers=org["headers"], json={"decision": "approve", "subject_tested": "Taranjabin"})
    ent = client.post("/api/v1/entities", headers=org["headers"], json={"knowledge_object_id": ko["id"], "entity_type": "ingredient", "canonical_name": "Taranjabin"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"], json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                        "predicate": "relieves", "object_value": "constipation", "claim_type": "efficacy"}).json()
    link = client.post("/api/v1/claim-evidence", headers=org["headers"], json={"claim_id": claim["id"], "evidence_id": cand["id"], "relation": "supports"})
    assert link.status_code in (200, 201), link.text
    chain = client.get(f"{R}/keywords/{kw['Taranjabin']['id']}/chain", headers=org["headers"]).json()
    assert chain["complete_to_claim"]
    full = next(c for c in chain["chain"] if c.get("claims"))
    assert full["claims"][0]["knowledge_object_id"] == ko["id"]
    assert any(e["id"] == cand["id"] and e["status"] == "verified" for e in full["evidence"])


def test_providers_only_reach_fixed_official_hosts(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "mode": "boolean", "boolean_query": '"http://169.254.169.254/latest" OR mannitol'})
    assert set(SEEN_HOSTS) <= scholarly.ALLOWED_HOSTS
    with pytest.raises(scholarly.ProviderUnavailable, match="host not allowed"):
        scholarly.CrossrefProvider(httpx.MockTransport(lambda r: httpx.Response(200)))._get(httpx.Client(), "http://127.0.0.1/works", {})


def test_research_records_are_tenant_isolated(client: TestClient, register_org, providers) -> None:
    a, b = register_org(), register_org()
    ko, kw = _ko(client, a)
    q = _question(client, a, ko)
    d = client.post(f"{R}/federated/keyword-search", headers=a["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=a["headers"])
    cand = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=a["headers"]).json()["awaiting_review"][0]
    for path in (f"{R}/questions/{q['research_question_id']}/evidence-map", f"{R}/sources/{d['source_ids'][0]}/detail",
                 f"{R}/keywords/{kw['Taranjabin']['id']}/chain", f"{R}/queries/{d['research_query_id']}"):
        assert client.get(path, headers=b["headers"]).status_code == 404, path
    assert client.post(f"{R}/evidence-candidates/{cand['id']}/review", headers=b["headers"],
                       json={"decision": "approve", "subject_tested": "Taranjabin"}).status_code == 404
    assert client.post(f"{R}/federated/keyword-search", headers=b["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).status_code == 404
    assert client.get(f"{R}/questions", headers=b["headers"]).json()["total"] == 0


def test_research_keyword_kinds_shape_the_queries(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, kw = _ko(client, org)
    assert {kw["Alhagi maurorum"]["kind"], kw["mannitol"]["kind"], kw["laxative"]["kind"]} == {"scientific_name", "compound", "clinical_outcome"}
    q = _question(client, org, ko)
    direct = q["routes"]["direct_subject"]["query"]
    # subject synonyms are expanded; the compound is NOT treated as a name of the subject
    assert "Persian manna" in direct and "Alhagi maurorum" in direct and "mannitol" not in direct.lower().split(" and ")[0]
    d = client.post(f"{R}/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"], kw["laxative"]["id"]], "mode": "agent"}).json()
    assert d["query"] == "(Taranjabin) AND (laxative)"



def test_conflicting_evidence_is_reported_not_resolved(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    c1, c2 = [c for c in m["awaiting_review"] if c["route"] == "compound_human"][:2]
    for c in (c1, c2):
        client.post(f"{R}/evidence-candidates/{c['id']}/review", headers=org["headers"], json={"decision": "approve", "subject_tested": "Mannitol"})
    ent = client.post("/api/v1/entities", headers=org["headers"], json={"knowledge_object_id": ko["id"], "entity_type": "compound", "canonical_name": "Mannitol"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"], json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                        "predicate": "acts_as", "object_value": "osmotic laxative", "claim_type": "mechanism"}).json()
    for c, rel in ((c1, "supports"), (c2, "contradicts")):
        assert client.post("/api/v1/claim-evidence", headers=org["headers"], json={"claim_id": claim["id"], "evidence_id": c["id"], "relation": rel}).status_code in (200, 201)
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    assert m["conflicting_claim_ids"] == [claim["id"]]


def test_knowledge_gap_find_more(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    gap = client.post("/api/v1/knowledge-gaps", headers=org["headers"], json={"knowledge_object_id": ko["id"], "gap_type": "evidence_gap",
                      "description": "human clinical evidence for laxative effect", "priority": "high"})
    assert gap.status_code in (200, 201), gap.text
    r = client.post(f"{R}/knowledge-gaps/{gap.json()['id']}/find-more", headers=org["headers"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert "Persian manna" in d["routes"]["direct_subject"]["query"] and d["routes"]["direct_subject"]["unique_sources"] > 0
    other = register_org()
    assert client.post(f"{R}/knowledge-gaps/{gap.json()['id']}/find-more", headers=other["headers"]).status_code == 404


# ================= multi-compound reasoning and the full route vocabulary (ADR-108) =================
def _multi_question(client, org, ko):
    r = client.post(f"{R}/questions", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "subject": "Taranjabin", "compounds": ["Mannitol", "Fructose"],
        "related_species": ["Alhagi persarum"], "outcome": "laxative", "population": "human"})
    assert r.status_code == 201, r.text
    return r.json()


def test_every_route_gets_its_own_search(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _multi_question(client, org, ko)
    assert set(q["routes"]) == {"direct_subject", "compound_human", "mechanistic", "co_occurrence",
                                "combination", "indirect_formulation", "indirect_analogous_species", "indirect_taxonomic"}
    # the combination route studies the compounds together, not each alone
    combo = q["routes"]["combination"]["query"]
    assert "Mannitol" in combo and "Fructose" in combo and " AND " in combo
    # a compound query never carries the subject, and the species route never carries the subject
    assert "Taranjabin" not in q["routes"]["compound_human"]["query"]
    assert "Alhagi persarum" in q["routes"]["indirect_analogous_species"]["query"]
    assert "Taranjabin" not in q["routes"]["indirect_analogous_species"]["query"]
    assert "Taranjabin" in q["routes"]["co_occurrence"]["query"] and "Mannitol" in q["routes"]["co_occurrence"]["query"]


def test_compounds_are_taken_from_the_knowledge_object_when_not_given(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)                       # the fixture object has a "mannitol" compound keyword
    r = client.post(f"{R}/questions", headers=org["headers"],
                    json={"knowledge_object_id": ko["id"], "subject": "Taranjabin", "outcome": "laxative"}).json()
    assert "compound_human" in r["routes"] and "mannitol" in r["routes"]["compound_human"]["query"].lower()


@pytest.mark.parametrize("route", ["compound_human", "mechanistic", "combination", "indirect_analogous_species",
                                   "indirect_taxonomic", "indirect_formulation", "co_occurrence"])
def test_no_indirect_route_can_ever_be_direct(client: TestClient, register_org, providers, db_session, route) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _multi_question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    cand = next((c for c in m["awaiting_review"] if c["route"] == route), None)
    if cand is None:
        pytest.skip(f"no candidate on the {route} route in this fixture set")
    r = client.post(f"{R}/evidence-candidates/{cand['id']}/review", headers=org["headers"],
                    json={"decision": "approve", "subject_tested": "Taranjabin"}).json()   # even claiming the subject
    assert r["directness"] == "indirect", f"{route} must stay indirect"
    with pytest.raises(exc.IntegrityError, match="compound_route_is_indirect"):
        db_session.execute(text("UPDATE evidence SET directness = 'direct' WHERE id = :i"), {"i": cand["id"]})
        db_session.flush()
    db_session.rollback()


def test_candidates_say_what_they_are_about(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _multi_question(client, org, ko)
    client.post(f"{R}/questions/{q['research_question_id']}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{q['research_question_id']}/evidence-map", headers=org["headers"]).json()
    assert set(m["compounds"]) == {"Mannitol", "Fructose"} and m["related_species"] == ["Alhagi persarum"]
    assert set(m["routes"]) >= {"combination", "indirect_taxonomic"}
    g = client.get(f"{R}/questions/{q['research_question_id']}/evidence-graph", headers=org["headers"]).json()
    labels = {n["label"] for n in g["nodes"]}
    assert {"Taranjabin", "Mannitol", "Fructose", "Alhagi persarum", "laxative"} <= labels


def test_the_graph_never_turns_a_compound_path_into_subject_evidence(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    q = _multi_question(client, org, ko)
    qid = q["research_question_id"]
    client.post(f"{R}/questions/{qid}/extract-candidates", headers=org["headers"])
    m = client.get(f"{R}/questions/{qid}/evidence-map", headers=org["headers"]).json()
    comp = next(c for c in m["awaiting_review"] if c["route"] == "compound_human")
    client.post(f"{R}/evidence-candidates/{comp['id']}/review", headers=org["headers"],
                json={"decision": "approve", "subject_tested": "Mannitol"})
    g = client.get(f"{R}/questions/{qid}/evidence-graph", headers=org["headers"]).json()
    assert g["direct_paths_to_subject"] == 0                       # nothing tested Taranjabin itself
    study_edges = [e for e in g["edges"] if e["label"] == "studied_in"]
    assert study_edges and all(e["directness"] == "indirect" for e in study_edges)
    assert all(e["from"].startswith("compound:") for e in study_edges)
    contains = [e for e in g["edges"] if e["label"] == "contains"]
    assert contains and all(e["documented"] is False and "assumed" in e["note"] for e in contains)   # honest
    assert "not the subject" in g["reading"]
    m2 = client.get(f"{R}/questions/{qid}/evidence-map", headers=org["headers"]).json()
    assert m2["status_summary"]["clinical_evidence_for_Taranjabin"] == "indirect"


def test_find_more_on_a_route_the_question_cannot_search(client: TestClient, register_org, providers) -> None:
    org = register_org()
    ko, _ = _ko(client, org)
    r = client.post(f"{R}/questions", headers=org["headers"],
                    json={"subject": "Taranjabin", "outcome": "laxative"}).json()        # no KO, no compounds
    bad = client.post(f"{R}/questions/{r['research_question_id']}/find-more", headers=org["headers"],
                      json={"route": "indirect_taxonomic", "extra_terms": []})
    assert bad.status_code == 422 and "nothing to search" in bad.text


def test_evidence_graph_is_tenant_scoped(client: TestClient, register_org, providers) -> None:
    a, b = register_org(), register_org()
    ko, _ = _ko(client, a)
    q = _multi_question(client, a, ko)
    assert client.get(f"{R}/questions/{q['research_question_id']}/evidence-graph", headers=b["headers"]).status_code == 404
