"""
THE GOLDEN TEST SUITE — Phase 5 edition (Research Engine).

Continues the pattern from every prior phase's tenant-isolation suite:
Organization A must never read, list, or write anything belonging to
Organization B — including creating a ResearchTask under another org's
ResearchProject (the two-hop case), and reaching another org's
ResearchTask indirectly through its parent project's id in a filter.
"""

from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import research_task_service


def _create_project(client: TestClient, headers: dict, name: str = "Project") -> dict:
    return client.post(
        "/api/v1/research/projects",
        json={"name": name, "objective": "x", "mode": "exploratory"},
        headers=headers,
    ).json()


def _create_task(client: TestClient, headers: dict, project_id: str) -> dict:
    return client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project_id, "task_type": "web_search", "query": "x"},
        headers=headers,
    ).json()


# --- Research Projects ------------------------------------------------


def test_user_cannot_read_another_orgs_research_project(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])

    response = client.get(f"/api/v1/research/projects/{project_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_research_project(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])

    response = client.patch(
        f"/api/v1/research/projects/{project_b['id']}", json={"name": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_transition_another_orgs_research_project(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])

    response = client.post(
        f"/api/v1/research/projects/{project_b['id']}/transition", json={"status": "active"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_research_project_list_never_includes_other_orgs_projects(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _create_project(client, org_a["headers"], "A Only")
    _create_project(client, org_b["headers"], "B Only")

    response = client.get("/api/v1/research/projects", headers=org_a["headers"])
    names = [p["name"] for p in response.json()["items"]]
    assert "A Only" in names
    assert "B Only" not in names


# --- Research Tasks (two-hop + indirect) ----------------------------------


def test_user_cannot_create_task_under_another_orgs_project(client: TestClient, register_org) -> None:
    """The two-hop case: fully authenticated within org A, but
    research_project_id points at org B."""
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])

    response = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project_b["id"], "task_type": "web_search", "query": "smuggled"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_research_task(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])
    task_b = _create_task(client, org_b["headers"], project_b["id"])

    response = client.get(f"/api/v1/research/tasks/{task_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_queue_or_cancel_another_orgs_research_task(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])
    task_b = _create_task(client, org_b["headers"], project_b["id"])

    update_response = client.patch(
        f"/api/v1/research/tasks/{task_b['id']}", json={"query": "hijacked"}, headers=org_a["headers"]
    )
    assert update_response.status_code == 404

    queue_response = client.post(f"/api/v1/research/tasks/{task_b['id']}/queue", headers=org_a["headers"])
    assert queue_response.status_code == 404

    cancel_response = client.post(f"/api/v1/research/tasks/{task_b['id']}/cancel", headers=org_a["headers"])
    assert cancel_response.status_code == 404


def test_indirect_access_via_project_id_filter_never_leaks_another_orgs_tasks(
    client: TestClient, register_org
) -> None:
    """A user from org A must not be able to discover org B's tasks by
    filtering ?research_project_id=<org B's project> — the list is
    scoped to org A's own tasks regardless of what project id is
    requested."""
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])
    _create_task(client, org_b["headers"], project_b["id"])

    response = client.get(
        f"/api/v1/research/tasks?research_project_id={project_b['id']}", headers=org_a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_research_task_list_never_includes_other_orgs_tasks(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_a = _create_project(client, org_a["headers"])
    project_b = _create_project(client, org_b["headers"])
    task_a = _create_task(client, org_a["headers"], project_a["id"])
    _create_task(client, org_b["headers"], project_b["id"])

    response = client.get("/api/v1/research/tasks", headers=org_a["headers"])
    ids = [t["id"] for t in response.json()["items"]]
    assert ids == [task_a["id"]]


def test_user_cannot_list_another_orgs_task_references(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])
    task_b = _create_task(client, org_b["headers"], project_b["id"])

    response = client.get(f"/api/v1/research/tasks/{task_b['id']}/references", headers=org_a["headers"])
    assert response.status_code == 404


def test_execute_research_task_cannot_cross_tenant_by_organization_id(
    client: TestClient, register_org, db_session: Session
) -> None:
    """Even calling the execution function directly with org A's own
    organization_id must 404 against a task_id that actually belongs to
    org B — the tenant check is on the task row itself, not implied by
    which caller happens to invoke the function."""
    org_a = register_org()
    org_b = register_org()
    project_b = _create_project(client, org_b["headers"])
    task_b = _create_task(client, org_b["headers"], project_b["id"])

    with pytest.raises(HTTPException) as exc_info:
        research_task_service.execute_research_task(
            db_session,
            task_id=UUID(task_b["id"]),
            organization_id=UUID(org_a["organization"]["id"]),
            actor_user_id=UUID(org_a["user"]["id"]),
        )
    assert exc_info.value.status_code == 404
