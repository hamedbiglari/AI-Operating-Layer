"""
The project's one real ResearchProvider: federated scholarly discovery.

Provider payloads below are FIXTURES written to the documented response formats of the Crossref
REST API (/works), NCBI E-utilities (esearch/esummary, retmode=json) and the Europe PMC REST API
(/search, resultType=core) — the same approach, and the same reason, as
tests/test_federated_research.py: those hosts are blocked by this sandbox's network allow-list,
so every run here goes through httpx.MockTransport and no test depends on the network.

What is under test is not the happy path but the five-way outcome section 18 demands the system
be able to tell apart, and the boundary section 12 draws: discovery registers sources, and
nothing else.
"""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.research import scholarly
from app.integrations.research.base import NotConfiguredResearchProvider, get_research_provider
from app.integrations.research.federated import FederatedResearchProvider
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.research_federation import ResearchHit, ResearchProviderRun, ResearchQuery
from app.models.research_task_reference import ResearchTaskReference
from app.models.source import Source
from app.services import federated_research_service as frs
from app.services import research_task_service

CROSSREF = {"status": "ok", "message": {"items": [
    {"DOI": "10.1000/ABC", "title": ["Mannitol as an osmotic laxative in adults"],
     "publisher": "Example Medical Press", "container-title": ["J Example Gastro"],
     "URL": "https://doi.org/10.1000/abc", "issued": {"date-parts": [[2019, 3]]},
     "abstract": "<jats:p>Randomised trial of oral mannitol in adults.</jats:p>"},
]}}
ESEARCH = {"esearchresult": {"count": "1", "idlist": ["111"]}}
ESUMMARY = {"result": {"uids": ["111"], "111": {
    "uid": "111", "title": "Mannitol as an osmotic laxative in adults.",
    "fulljournalname": "J Example Gastro", "pubdate": "2019 Mar",
    "articleids": [{"idtype": "pubmed", "value": "111"}, {"idtype": "doi", "value": "10.1000/abc"}]}}}
EUROPEPMC = {"hitCount": 1, "resultList": {"result": [
    {"id": "222", "source": "MED", "pmid": "222", "title": "Taranjabin in functional constipation.",
     "abstractText": "Adults received taranjabin syrup or placebo for four weeks.",
     "isOpenAccess": "Y", "pubYear": "2021", "journalInfo": {"journal": {"title": "Iran J Trad Med"}}},
]}}
EMPTY_CROSSREF = {"status": "ok", "message": {"items": []}}
EMPTY_ESEARCH = {"esearchresult": {"count": "0", "idlist": []}}
EMPTY_EUROPEPMC = {"hitCount": 0, "resultList": {"result": []}}


def _handler(*, empty: bool = False, fail: set[str] | None = None):
    failing = fail or set()
    seen: list[str] = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.host)
        if req.url.host in failing:
            raise httpx.ConnectError("blocked", request=req)
        if req.url.host == "api.crossref.org":
            return httpx.Response(200, json=EMPTY_CROSSREF if empty else CROSSREF)
        if req.url.host == "eutils.ncbi.nlm.nih.gov":
            if req.url.path.endswith("esearch.fcgi"):
                return httpx.Response(200, json=EMPTY_ESEARCH if empty else ESEARCH)
            return httpx.Response(200, json=ESUMMARY)
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json=EMPTY_EUROPEPMC if empty else EUROPEPMC)
        return httpx.Response(404)

    h.seen = seen
    return h


def _register(monkeypatch, handler):
    monkeypatch.setattr(frs, "default_providers",
                        lambda transport=None: scholarly.default_providers(httpx.MockTransport(handler)))
    return handler


@pytest.fixture()
def answering(monkeypatch):
    """Every scholarly API answers with the fixtures above; the web provider stays unconfigured,
    exactly as it is in this repository."""
    return _register(monkeypatch, _handler())


def _project_and_task(client: TestClient, headers: dict, query: str) -> dict:
    project = client.post("/api/v1/research/projects", headers=headers,
                          json={"name": "P", "objective": "x", "mode": "exploratory"}).json()
    return client.post("/api/v1/research/tasks", headers=headers,
                       json={"research_project_id": project["id"], "task_type": "web_search",
                             "query": query}).json()


def _execute(db_session: Session, client: TestClient, org: dict,
             query: str = "mannitol laxative adults"):
    """Queue and run one task the way production does, in this test's own session."""
    task = _project_and_task(client, org["headers"], query)
    org_id, user_id = uuid.UUID(org["organization"]["id"]), uuid.UUID(org["user"]["id"])
    row = research_task_service.get_research_task_or_404(
        db_session, task_id=uuid.UUID(task["id"]), organization_id=org_id)
    research_task_service.queue_research_task(db_session, task=row, actor_user_id=user_id)
    return research_task_service.execute_research_task(
        db_session, task_id=uuid.UUID(task["id"]), organization_id=org_id, actor_user_id=user_id)


# --- registration -----------------------------------------------------------------------------

def test_the_registered_provider_is_the_federated_one_when_a_task_context_exists(
        client, register_org, db_session):
    org = register_org()
    task = _project_and_task(client, org["headers"], "q")
    org_id = uuid.UUID(org["organization"]["id"])
    row = research_task_service.get_research_task_or_404(
        db_session, task_id=uuid.UUID(task["id"]), organization_id=org_id)

    provider = get_research_provider(db=db_session, organization_id=org_id, task=row)

    assert isinstance(provider, FederatedResearchProvider)


def test_without_an_execution_context_there_is_nothing_to_bind_and_it_says_so():
    """A discovery run writes rows; asked for a provider with no session, tenant or task, the
    registration point reports 'not configured' instead of guessing one."""
    assert isinstance(get_research_provider(), NotConfiguredResearchProvider)
    assert isinstance(get_research_provider(db=object(), organization_id=None, task=None),
                      NotConfiguredResearchProvider)


# --- the five outcomes ------------------------------------------------------------------------

def test_a_task_with_no_explicit_provider_really_searches_and_registers_sources(
        client, register_org, db_session, answering):
    org = register_org()
    before = db_session.execute(select(func.count()).select_from(Source)).scalar_one()

    task = _execute(db_session, client, org)

    assert task.status.value == "completed"
    assert task.result["outcome_status"] == "result_found"
    assert task.result["reference_count"] >= 1
    after = db_session.execute(select(func.count()).select_from(Source)).scalar_one()
    assert after > before, "a discovery run that found records must leave sources behind"

    refs = db_session.execute(select(ResearchTaskReference).where(
        ResearchTaskReference.research_task_id == task.id)).scalars().all()
    assert refs
    assert {r.reference_type.value for r in refs} == {"source"}
    assert {r.role.value for r in refs} == {"output"}
    for r in refs:
        src = db_session.get(Source, r.reference_id)
        assert src is not None and src.organization_id == task.organization_id


def test_unreachable_providers_are_a_failure_not_a_missing_configuration(
        client, register_org, db_session, monkeypatch):
    _register(monkeypatch, _handler(fail={"api.crossref.org", "eutils.ncbi.nlm.nih.gov",
                                          "www.ebi.ac.uk"}))
    org = register_org()

    task = _execute(db_session, client, org)

    assert task.status.value == "failed"
    assert task.result["outcome_status"] == "provider_failed"
    assert "crossref" in task.result["summary"]
    assert task.result["reference_count"] == 0


def test_only_unconfigured_providers_report_not_configured(client, register_org, db_session,
                                                           monkeypatch):
    """The deployment section 18 describes: nothing to ask. It must not be reported as an outage."""
    monkeypatch.setattr(frs, "default_providers",
                        lambda transport=None: [scholarly.NotConfiguredWebProvider()])
    org = register_org()

    task = _execute(db_session, client, org)

    assert task.status.value == "failed"
    assert task.result["outcome_status"] == "not_configured"
    assert "web" in task.result["summary"]


def test_providers_that_answer_with_nothing_report_no_result_found(client, register_org, db_session,
                                                                   monkeypatch):
    _register(monkeypatch, _handler(empty=True))
    org = register_org()
    before = db_session.execute(select(func.count()).select_from(Source)).scalar_one()

    task = _execute(db_session, client, org)

    assert task.status.value == "failed"
    assert task.result["outcome_status"] == "no_result_found"
    assert db_session.execute(select(func.count()).select_from(Source)).scalar_one() == before


def test_a_query_with_no_searchable_words_is_not_sent_to_any_provider(client, register_org,
                                                                      db_session, answering):
    org = register_org()

    task = _execute(db_session, client, org, query='AND OR NOT ("")')

    assert task.result["outcome_status"] == "no_result_found"
    assert answering.seen == [], "nothing should have been asked"


# --- the trail --------------------------------------------------------------------------------

def test_the_run_leaves_the_same_federation_trail_the_research_endpoints_write(
        client, register_org, db_session, answering):
    org = register_org()

    task = _execute(db_session, client, org)

    query = db_session.execute(select(ResearchQuery).where(
        ResearchQuery.research_task_id == task.id)).scalars().one()
    assert query.mode == "single" and query.route == "general"
    runs = db_session.execute(select(ResearchProviderRun).where(
        ResearchProviderRun.research_query_id == query.id)).scalars().all()
    assert {r.provider: r.status for r in runs} == {
        "crossref": "ok", "pubmed": "ok", "europepmc": "ok", "web": "not_configured"}
    hits = db_session.execute(select(ResearchHit).where(
        ResearchHit.provider_run_id.in_([r.id for r in runs]))).scalars().all()
    assert hits, "a returned record must be recorded as a hit against its provider run"


def test_search_operators_are_dropped_from_a_natural_language_question(
        client, register_org, db_session, answering):
    """A chat question is not a boolean query; its operators and quotes would otherwise be sent to
    the providers as literal search terms."""
    org = register_org()

    task = _execute(db_session, client, org,
                    query='what does the evidence say about "mannitol" AND (laxative) use?')

    query = db_session.execute(select(ResearchQuery).where(
        ResearchQuery.research_task_id == task.id)).scalars().one()
    assert '"' not in query.query_text and "(" not in query.query_text
    assert " AND " not in f" {query.query_text} "
    assert "mannitol" in query.query_text and "laxative" in query.query_text


def test_re_running_the_same_query_adds_no_sources_but_still_reports_what_it_confirmed(
        client, register_org, db_session, answering):
    org = register_org()
    first = _execute(db_session, client, org)
    after_first = db_session.execute(select(func.count()).select_from(Source)).scalar_one()

    second = _execute(db_session, client, org)

    assert second.status.value == "completed"
    assert second.result["raw"]["new_sources"] == 0
    assert second.result["raw"]["merged_duplicates"] >= 1
    assert second.result["reference_count"] == first.result["reference_count"]
    assert db_session.execute(select(func.count()).select_from(Source)).scalar_one() == after_first


# --- the section 12 boundary ------------------------------------------------------------------

def test_discovery_creates_no_claim_and_no_evidence(client, register_org, db_session, answering):
    org = register_org()
    org_id = uuid.UUID(org["organization"]["id"])

    _execute(db_session, client, org)

    assert db_session.execute(select(func.count()).select_from(Claim).where(
        Claim.organization_id == org_id)).scalar_one() == 0
    assert db_session.execute(select(func.count()).select_from(Evidence).where(
        Evidence.organization_id == org_id)).scalar_one() == 0


def test_a_discovered_source_never_claims_full_text(client, register_org, db_session, answering):
    org = register_org()

    task = _execute(db_session, client, org)

    refs = db_session.execute(select(ResearchTaskReference).where(
        ResearchTaskReference.research_task_id == task.id)).scalars().all()
    assert refs
    for r in refs:
        src = db_session.get(Source, r.reference_id)
        assert src.full_text_accessed is False
        assert src.content_access in ("metadata_only", "abstract_only")
        assert src.review_status == "not_reviewed"
