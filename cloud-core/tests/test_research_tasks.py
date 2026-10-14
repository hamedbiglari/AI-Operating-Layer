"""
Integration tests for ResearchTask: creation under a project (the
two-hop tenant check), edit-only-while-PENDING, and the queue/cancel
lifecycle actions.

The `/queue` endpoint dispatches a real Celery job via `.delay()`. In
this suite (see conftest.py's `_celery_eager_mode`) that runs the real
task body synchronously, in-process — but `app/workers/tasks.py`
deliberately opens its OWN database session (SessionLocal), separate
from the transactional, rolled-back session these HTTP tests run
against (see tests/conftest.py's `db_session`/`client` docstring). A
task created inside a not-yet-committed test transaction is therefore
invisible to that second connection — this is a property of the
test-isolation strategy, not of the endpoint. `_no_op_dispatch` patches
`.delay` in tests that only care about the QUEUE transition itself; the
Celery task's actual body (the real execution logic) is exercised
directly, same-session, in test_research_execution.py instead.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def _no_op_dispatch(monkeypatch: pytest.MonkeyPatch):
    from app.workers.tasks import execute_research_task_job

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(execute_research_task_job, "delay", lambda task_id, org_id: calls.append((task_id, org_id)))
    return calls


def _create_project(client: TestClient, headers: dict, name: str = "Project") -> dict:
    return client.post(
        "/api/v1/research/projects",
        json={"name": name, "objective": "x", "mode": "exploratory"},
        headers=headers,
    ).json()


def test_create_task_under_project(client: TestClient, register_org) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])

    response = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "Is taranjabin sweet?"},
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["research_project_id"] == project["id"]
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None


def test_create_task_under_nonexistent_project_returns_404(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/research/tasks",
        json={
            "research_project_id": "00000000-0000-0000-0000-000000000000",
            "task_type": "web_search",
            "query": "x",
        },
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_update_pending_task(client: TestClient, register_org) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "old query"},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/research/tasks/{task['id']}", json={"query": "new query"}, headers=org["headers"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["query"] == "new query"


def test_queue_transitions_pending_to_queued_and_dispatches(
    client: TestClient, register_org, _no_op_dispatch
) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=org["headers"],
    ).json()

    response = client.post(f"/api/v1/research/tasks/{task['id']}/queue", headers=org["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert len(_no_op_dispatch) == 1
    assert _no_op_dispatch[0][0] == task["id"]


def test_cannot_edit_task_once_queued(client: TestClient, register_org, _no_op_dispatch) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/research/tasks/{task['id']}/queue", headers=org["headers"])

    response = client.patch(
        f"/api/v1/research/tasks/{task['id']}", json={"query": "too late"}, headers=org["headers"]
    )
    assert response.status_code == 409


def test_double_queue_is_rejected(client: TestClient, register_org, _no_op_dispatch) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/research/tasks/{task['id']}/queue", headers=org["headers"])

    response = client.post(f"/api/v1/research/tasks/{task['id']}/queue", headers=org["headers"])
    assert response.status_code == 422


def test_cancel_pending_task(client: TestClient, register_org) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=org["headers"],
    ).json()

    response = client.post(f"/api/v1/research/tasks/{task['id']}/cancel", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancelled_task_cannot_be_queued(client: TestClient, register_org) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    task = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=org["headers"],
    ).json()
    client.post(f"/api/v1/research/tasks/{task['id']}/cancel", headers=org["headers"])

    response = client.post(f"/api/v1/research/tasks/{task['id']}/queue", headers=org["headers"])
    assert response.status_code == 422


def test_list_tasks_filtered_by_project_and_status(client: TestClient, register_org) -> None:
    org = register_org()
    project_a = _create_project(client, org["headers"], "A")
    project_b = _create_project(client, org["headers"], "B")
    task_a = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project_a["id"], "task_type": "web_search", "query": "a"},
        headers=org["headers"],
    ).json()
    client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project_b["id"], "task_type": "web_search", "query": "b"},
        headers=org["headers"],
    )

    response = client.get(
        f"/api/v1/research/tasks?research_project_id={project_a['id']}", headers=org["headers"]
    )
    ids = [t["id"] for t in response.json()["items"]]
    assert ids == [task_a["id"]]

    by_status = client.get("/api/v1/research/tasks?status=pending", headers=org["headers"]).json()
    assert by_status["total"] == 2


def test_viewer_cannot_create_research_task(client: TestClient, register_org) -> None:
    org = register_org()
    project = _create_project(client, org["headers"])
    client.post(
        "/api/v1/users",
        json={"email": "task-viewer@example.dev", "name": "Viewer", "password": "supersecret123", "role": "viewer"},
        headers=org["headers"],
    )
    login = client.post("/api/v1/auth/login", data={"username": "task-viewer@example.dev", "password": "supersecret123"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/research/tasks",
        json={"research_project_id": project["id"], "task_type": "web_search", "query": "x"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
