"""
Tests for research_task_service.execute_research_task — called
DIRECTLY, in the same DB session the test's `client` fixture uses (see
test_research_tasks.py's module docstring for why: the Celery task
wrapper opens its own separate connection that a rolled-back test
transaction is invisible to, so exercising the real execution logic
same-session, without going through `.delay()`, is the precise way to
test it here).
"""

from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest

from app.integrations.research.base import ResearchOutcome, ResearchOutcomeStatus, ResearchReference
from app.services import research_task_service


def _create_project_and_task(client: TestClient, headers: dict) -> dict:
    project = client.post(
        "/api/v1/research/projects",
        json={"name": "P", "objective": "x", "mode": "exploratory"},
        headers=headers,
    ).json()
    return client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "Is taranjabin sweet?"},
        headers=headers,
    ).json()


def _queue_directly(db_session: Session, *, task_id: UUID, organization_id: UUID, actor_user_id: UUID) -> None:
    """Moves a task PENDING -> QUEUED via the service layer, same
    session, with no Celery dispatch side effect — matching the real
    production sequence (a task is always QUEUED before anything ever
    calls execute_research_task on it) without needing a second DB
    connection in these same-session tests."""
    task = research_task_service.get_research_task_or_404(db_session, task_id=task_id, organization_id=organization_id)
    research_task_service.queue_research_task(db_session, task=task, actor_user_id=actor_user_id)


class _FakeProvider:
    def __init__(self, outcome: ResearchOutcome) -> None:
        self._outcome = outcome

    def run(self, *, task_type: str, query: str) -> ResearchOutcome:
        return self._outcome


def test_execute_with_no_provider_configured_fails_honestly(
    client: TestClient, register_org, db_session: Session, monkeypatch
) -> None:
    """A task executed with no `provider` argument uses whatever
    get_research_provider() registers — today the federated scholarly
    provider. This test is about the deployment where there is nothing
    to ask: every registered provider reports itself unconfigured, so
    the only honest outcome is `not_configured`, and the task fails
    rather than reporting a result it never got. The provider list is
    narrowed here rather than left to chance, so the assertion does not
    depend on whether this machine can reach the scholarly APIs."""
    from app.integrations.research import scholarly
    from app.services import federated_research_service

    monkeypatch.setattr(federated_research_service, "default_providers",
                        lambda transport=None: [scholarly.NotConfiguredWebProvider()])

    org = register_org()
    task = _create_project_and_task(client, org["headers"])
    org_id, user_id = UUID(org["organization"]["id"]), UUID(org["user"]["id"])
    _queue_directly(db_session, task_id=UUID(task["id"]), organization_id=org_id, actor_user_id=user_id)

    result_task = research_task_service.execute_research_task(
        db_session,
        task_id=UUID(task["id"]),
        organization_id=org_id,
        actor_user_id=user_id,
    )

    assert result_task.status.value == "failed"
    assert result_task.result["outcome_status"] == "not_configured"
    assert result_task.started_at is not None
    assert result_task.completed_at is not None


def test_execute_with_fake_provider_result_found_persists_references(
    client: TestClient, register_org, db_session: Session
) -> None:
    org = register_org()
    task = _create_project_and_task(client, org["headers"])
    source = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "A Source"}, headers=org["headers"]
    ).json()

    provider = _FakeProvider(
        ResearchOutcome(
            status=ResearchOutcomeStatus.RESULT_FOUND,
            summary="Found a relevant source.",
            references=[ResearchReference(reference_type="source", reference_id=source["id"], role="output")],
            raw={"provider": "fake"},
        )
    )

    org_id, user_id = UUID(org["organization"]["id"]), UUID(org["user"]["id"])
    _queue_directly(db_session, task_id=UUID(task["id"]), organization_id=org_id, actor_user_id=user_id)

    result_task = research_task_service.execute_research_task(
        db_session,
        task_id=UUID(task["id"]),
        organization_id=org_id,
        actor_user_id=user_id,
        provider=provider,
    )

    assert result_task.status.value == "completed"
    assert result_task.result["outcome_status"] == "result_found"
    assert result_task.result["reference_count"] == 1

    refs, total = research_task_service.list_task_references(
        db_session, task_id=UUID(task["id"]), organization_id=org_id, limit=50, offset=0
    )
    assert total == 1
    assert str(refs[0].reference_id) == source["id"]
    assert refs[0].reference_type.value == "source"
    assert refs[0].role.value == "output"


def test_execute_rejects_reference_to_another_orgs_resource(
    client: TestClient, register_org, db_session: Session
) -> None:
    org_a = register_org()
    org_b = register_org()
    task = _create_project_and_task(client, org_a["headers"])
    source_b = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "B Source"}, headers=org_b["headers"]
    ).json()

    provider = _FakeProvider(
        ResearchOutcome(
            status=ResearchOutcomeStatus.RESULT_FOUND,
            references=[ResearchReference(reference_type="source", reference_id=source_b["id"], role="output")],
        )
    )

    org_id, user_id = UUID(org_a["organization"]["id"]), UUID(org_a["user"]["id"])
    _queue_directly(db_session, task_id=UUID(task["id"]), organization_id=org_id, actor_user_id=user_id)

    with pytest.raises(HTTPException) as exc_info:
        research_task_service.execute_research_task(
            db_session,
            task_id=UUID(task["id"]),
            organization_id=org_id,
            actor_user_id=user_id,
            provider=provider,
        )
    assert exc_info.value.status_code == 404


def test_execute_referencing_existing_evidence_does_not_verify_it(
    client: TestClient, register_org, db_session: Session
) -> None:
    """Section 12's boundary, concretely: a research task discovering
    (referencing) an existing Evidence row must never move that row's
    own review status. Discovery is not verification."""
    org = register_org()
    task = _create_project_and_task(client, org["headers"])
    source = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "A Source"}, headers=org["headers"]
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "summary": "A candidate finding."},
        headers=org["headers"],
    ).json()
    assert evidence["status"] == "draft"
    assert evidence["human_reviewed"] is False

    provider = _FakeProvider(
        ResearchOutcome(
            status=ResearchOutcomeStatus.RESULT_FOUND,
            references=[ResearchReference(reference_type="evidence", reference_id=evidence["id"], role="output")],
        )
    )
    org_id, user_id = UUID(org["organization"]["id"]), UUID(org["user"]["id"])
    _queue_directly(db_session, task_id=UUID(task["id"]), organization_id=org_id, actor_user_id=user_id)
    research_task_service.execute_research_task(
        db_session,
        task_id=UUID(task["id"]),
        organization_id=org_id,
        actor_user_id=user_id,
        provider=provider,
    )

    refreshed_evidence = client.get(f"/api/v1/evidence/{evidence['id']}", headers=org["headers"]).json()
    assert refreshed_evidence["status"] == "draft"
    assert refreshed_evidence["human_reviewed"] is False


def test_cannot_execute_an_already_terminal_task(client: TestClient, register_org, db_session: Session) -> None:
    org = register_org()
    task = _create_project_and_task(client, org["headers"])
    client.post(f"/api/v1/research/tasks/{task['id']}/cancel", headers=org["headers"])

    with pytest.raises(research_task_service.InvalidResearchTaskTransitionError):
        research_task_service.execute_research_task(
            db_session,
            task_id=UUID(task["id"]),
            organization_id=UUID(org["organization"]["id"]),
            actor_user_id=UUID(org["user"]["id"]),
        )
