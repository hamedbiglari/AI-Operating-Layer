"""Carrying out an approved chat research request — §13.6 steps 5-9 (ADR-130).

The point of these tests is the honesty of the outcome, not the happy path. A deployment with no
research provider is the normal case in this repository, and what it must produce is a request that
says plainly that nothing was researched — never a `completed` request with nothing behind it.
"""
import uuid

import pytest
from sqlalchemy import select

from app.integrations.research.base import (
    ResearchOutcome, ResearchOutcomeStatus, ResearchReference,
)
from app.models.conversation import (
    ChatSettings, Conversation, ConversationMessage, ConversationResearchRequest,
)
from app.models.enums import ResearchMode, ResearchTaskStatus
from app.models.research_project import ResearchProject
from app.models.research_task import ResearchTask
from app.models.source import Source
from app.models.user import User
from app.services import chat_research_service


# --- doubles -------------------------------------------------------------------------------

class Provider:
    """A ResearchProvider under the test's control. It reports; it never writes knowledge."""

    def __init__(self, status, sources=(), summary="done"):
        self.status = status
        self.sources = list(sources)
        self.summary = summary
        self.calls = []

    def run(self, *, task_type, query):
        self.calls.append((task_type, query))
        return ResearchOutcome(
            status=self.status,
            summary=self.summary,
            references=[ResearchReference(reference_type="source", reference_id=str(s), role="output")
                        for s in self.sources],
        )


@pytest.fixture()
def org(register_org):
    return register_org()


def _user(db_session, org) -> User:
    return db_session.get(User, uuid.UUID(org["user"]["id"]))


def _enable(db_session, org) -> ChatSettings:
    row = ChatSettings(organization_id=uuid.UUID(org["organization"]["id"]), enabled=True)
    db_session.add(row)
    db_session.flush()
    return row


def _request(db_session, org, *, state="approved", question="what does the evidence say about x?"):
    """A conversation, a turn, and a research request in the state under test."""
    org_id = uuid.UUID(org["organization"]["id"])
    user = _user(db_session, org)
    convo = Conversation(organization_id=org_id, user_id=user.id, title="t", state="active")
    db_session.add(convo)
    db_session.flush()
    msg = ConversationMessage(organization_id=org_id, conversation_id=convo.id, position=1,
                              role="assistant", text="not enough evidence",
                              answer_state="NEEDS_WEB_RESEARCH")
    db_session.add(msg)
    db_session.flush()
    req = ConversationResearchRequest(
        organization_id=org_id, user_id=user.id, conversation_id=convo.id, message_id=msg.id,
        question=question, proposed_scope={"terms": ["evidence", "about"]}, state=state,
        authorization_basis="user_approved" if state == "approved" else None,
        # The schema requires a decision timestamp on any state that implies one was made.
        decided_at=msg.created_at if state in ("approved", "running", "completed") else None)
    db_session.add(req)
    db_session.flush()
    return req


def _source(db_session, org) -> Source:
    src = Source(organization_id=uuid.UUID(org["organization"]["id"]),
                 title="A paper", source_type="scientific_paper")
    db_session.add(src)
    db_session.flush()
    return src


# --- the normal case in this repository: no provider -----------------------------------------

def test_with_no_provider_configured_the_request_fails_and_says_so(client, org, db_session):
    _enable(db_session, org)
    req = _request(db_session, org)

    out = chat_research_service.run(db_session, req=req,
                                    provider=Provider(ResearchOutcomeStatus.NOT_CONFIGURED,
                                                      summary="No research provider is configured."))

    assert out.state == "failed", "a request that researched nothing must not report completion"
    assert "provider" in (out.error or "").lower()
    assert out.sources_added == 0
    assert out.reanswer_message_id is None


def test_a_provider_failure_is_reported_not_swallowed(client, org, db_session):
    _enable(db_session, org)
    req = _request(db_session, org)
    out = chat_research_service.run(db_session, req=req,
                                    provider=Provider(ResearchOutcomeStatus.PROVIDER_FAILED,
                                                      summary="upstream returned 500"))
    assert out.state == "failed" and out.error


def test_a_failed_request_always_carries_a_reason(client, org, db_session):
    """The schema refuses `failed` with a null error; this is the service honouring it."""
    _enable(db_session, org)
    req = _request(db_session, org)
    out = chat_research_service.run(db_session, req=req,
                                    provider=Provider(ResearchOutcomeStatus.RESULT_INACCESSIBLE,
                                                      summary="paywalled"))
    assert out.state == "failed"
    assert out.error is not None and out.error.strip() != ""


# --- research ran, but found nothing ------------------------------------------------------------

def test_nothing_found_completes_without_spending_a_model_call(client, org, db_session):
    _enable(db_session, org)
    req = _request(db_session, org)

    out = chat_research_service.run(db_session, req=req,
                                    provider=Provider(ResearchOutcomeStatus.NO_RESULT_FOUND))

    # NO_RESULT_FOUND is not a task failure, but it adds no sources, so there is nothing to
    # re-answer with and no reason to pay for a second answer.
    assert out.sources_added == 0
    assert out.reanswer_message_id is None, "re-answering an unchanged knowledge base is not progress"
    assert out.state in ("completed", "failed")


# --- research ran and registered sources ----------------------------------------------------------

def test_sources_are_counted_from_the_research_layer(client, org, db_session, monkeypatch):
    _enable(db_session, org)
    req = _request(db_session, org)
    sources = [_source(db_session, org).id, _source(db_session, org).id]

    # The re-answer is the chat pipeline's job and is exercised in test_chat.py; here it is replaced
    # so this test is about registration and reconciliation only.
    answered = {}

    def fake_ask(db, *, convo, user, question, **kw):
        answered["question"] = question
        msg = ConversationMessage(organization_id=convo.organization_id, conversation_id=convo.id,
                                  position=99, role="assistant", text="now answerable",
                                  answer_state="ANSWERED_FROM_KNOWLEDGE")
        db.add(msg)
        db.flush()
        return msg

    monkeypatch.setattr(chat_research_service.chat_service, "ask", fake_ask)

    out = chat_research_service.run(
        db_session, req=req,
        provider=Provider(ResearchOutcomeStatus.RESULT_FOUND, sources=sources))

    assert out.sources_added == 2
    assert out.state == "completed"
    assert out.reanswer_message_id is not None, "new sources must lead to a new answer"
    assert answered["question"] == req.question, "the re-answer must ask the original question"


def test_the_research_runs_through_the_existing_research_layer(client, org, db_session, monkeypatch):
    """No second research engine: a real project and a real task are created and executed."""
    _enable(db_session, org)
    req = _request(db_session, org)
    provider = Provider(ResearchOutcomeStatus.NO_RESULT_FOUND)

    chat_research_service.run(db_session, req=req, provider=provider)

    assert provider.calls, "the provider was never asked to do anything"
    assert provider.calls[0][1] == req.question

    project = db_session.get(ResearchProject, req.research_project_id)
    assert project is not None, "the request must point at the project that did the work"
    assert project.organization_id == req.organization_id
    tasks = db_session.execute(select(ResearchTask).where(
        ResearchTask.research_project_id == project.id)).scalars().all()
    assert len(tasks) == 1 and tasks[0].query == req.question
    assert tasks[0].status in (ResearchTaskStatus.COMPLETED, ResearchTaskStatus.FAILED)


def test_the_project_mode_matches_whether_a_gap_was_recorded(client, org, db_session):
    _enable(db_session, org)
    req = _request(db_session, org)
    assert req.knowledge_gap_id is None
    chat_research_service.run(db_session, req=req,
                              provider=Provider(ResearchOutcomeStatus.NO_RESULT_FOUND))
    project = db_session.get(ResearchProject, req.research_project_id)
    # gap_driven would be a lie here, and the schema would refuse it.
    assert project.mode == ResearchMode.USER_DRIVEN


# --- only an approved request runs ------------------------------------------------------------------

@pytest.mark.parametrize("state", ["pending_approval", "rejected", "cancelled", "completed", "running"])
def test_a_request_that_is_not_approved_is_left_alone(client, org, db_session, state):
    _enable(db_session, org)
    req = _request(db_session, org, state=state)
    provider = Provider(ResearchOutcomeStatus.RESULT_FOUND)

    out = chat_research_service.run(db_session, req=req, provider=provider)

    assert out.state == state, "running an unapproved request would bypass the authorisation"
    assert not provider.calls
    assert out.research_project_id is None


def test_running_the_same_request_twice_does_not_research_twice(client, org, db_session):
    _enable(db_session, org)
    req = _request(db_session, org)
    first = Provider(ResearchOutcomeStatus.NO_RESULT_FOUND)
    chat_research_service.run(db_session, req=req, provider=first)
    assert len(first.calls) == 1

    second = Provider(ResearchOutcomeStatus.RESULT_FOUND)
    chat_research_service.run(db_session, req=req, provider=second)
    assert not second.calls, "a finished request must not be run again"


# --- tenant scoping -----------------------------------------------------------------------------------

def test_run_by_id_uses_the_provider_it_is_given(client, org, db_session):
    """The worker entry point must pass its provider through; dropping it would silently fall back
    to the registered one and make every test of this path meaningless."""
    _enable(db_session, org)
    req = _request(db_session, org)
    provider = Provider(ResearchOutcomeStatus.NO_RESULT_FOUND)

    chat_research_service.run_by_id(db_session, request_id=req.id,
                                    organization_id=req.organization_id, provider=provider)

    assert provider.calls, "run_by_id ignored the provider it was handed"


def test_another_tenants_request_is_not_run(client, register_org, db_session):
    a, b = register_org(), register_org()
    _enable(db_session, a)
    req = _request(db_session, a)

    out = chat_research_service.run_by_id(
        db_session, request_id=req.id, organization_id=uuid.UUID(b["organization"]["id"]))

    assert out is None
    db_session.refresh(req)
    assert out is None and req.state == "approved"

# --- the approval endpoint actually starts it ----------------------------------------------------------

def test_approving_through_the_api_queues_the_work(client, org, db_session, monkeypatch):
    """Celery runs eagerly in this suite, so `.delay` executes the real task body in-process. What is
    asserted is that approval reaches it at all — before ADR-130 nothing did."""
    _enable(db_session, org)
    req = _request(db_session, org, state="pending_approval")
    db_session.commit()

    started = []
    import app.workers.tasks as tasks
    monkeypatch.setattr(tasks.run_chat_research_request, "delay",
                        lambda rid, oid: started.append((rid, oid)))

    response = client.post(f"/api/v1/chat/research-requests/{req.id}/approve", headers=org["headers"])

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "approved"
    assert started == [(str(req.id), str(req.organization_id))], "approval did not start the research"


def test_a_broker_that_is_down_does_not_undo_the_approval(client, org, db_session, monkeypatch):
    """The user's decision is already committed. A queueing failure must not roll it back."""
    _enable(db_session, org)
    req = _request(db_session, org, state="pending_approval")
    db_session.commit()

    import app.workers.tasks as tasks

    def boom(rid, oid):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(tasks.run_chat_research_request, "delay", boom)

    response = client.post(f"/api/v1/chat/research-requests/{req.id}/approve", headers=org["headers"])

    assert response.status_code == 200, response.text
    db_session.refresh(req)
    assert req.state == "approved", "the decision must survive a broker outage"


def test_rejecting_starts_nothing(client, org, db_session, monkeypatch):
    _enable(db_session, org)
    req = _request(db_session, org, state="pending_approval")
    db_session.commit()

    started = []
    import app.workers.tasks as tasks
    monkeypatch.setattr(tasks.run_chat_research_request, "delay",
                        lambda rid, oid: started.append(rid))

    response = client.post(f"/api/v1/chat/research-requests/{req.id}/reject", headers=org["headers"])
    assert response.status_code == 200 and response.json()["state"] == "rejected"
    assert not started

