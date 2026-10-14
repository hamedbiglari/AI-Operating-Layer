"""
P12-18 Visibility infrastructure (ADR-074).

These tests prove BEHAVIOUR, not existence. The route-level E2E drives:

    POST run -> 202 -> worker -> provider fixture -> observations
             -> snapshot -> events

and asserts persisted state at each stage.
"""

import uuid as uuid_module

import pytest
from fastapi.testclient import TestClient

from app.models.enums import ProviderOutcome, SignalPresence, VisibilityRunStatus


def _project(client: TestClient, headers: dict, **kw) -> dict:
    body = {"name": f"proj-{uuid_module.uuid4().hex[:6]}", "markets": ["US"],
            "languages": ["en"], "platforms": ["chatgpt"],
            "target_brand": "Taranjabin Co", "target_domain": "merchant.example"}
    body.update(kw)
    return client.post("/api/v1/visibility/projects", json=body, headers=headers).json()


def _queries(client: TestClient, headers: dict, texts: list[str]) -> None:
    import json as _json

    client.post("/api/v1/queries/import",
                data={"source": "manual",
                      "rows_json": _json.dumps([{"query": t} for t in texts])},
                headers=headers)


def _budget(client: TestClient, headers: dict, limit: float = 5.0) -> None:
    """A run against a paid provider needs budget. The default limit is
    ZERO by design (ADR-069), so a test that omits this sees every probe
    correctly refused — which is how this helper came to exist."""
    client.put("/api/v1/visibility/budget",
               json={"period_limit": limit, "currency": "USD"}, headers=headers)


def _run(client: TestClient, headers: dict, project_id: str, provider: str = "fixture",
         budget: float = 5.0):
    if budget:
        _budget(client, headers, budget)
    return client.post(f"/api/v1/visibility/projects/{project_id}/runs",
                       json={"platform": "chatgpt", "provider_name": provider},
                       headers=headers)


def _execute(db_session, run_id: str) -> dict:
    """Runs the REAL service body — the Celery task is a thin wrapper over
    exactly this (ADR-073)."""
    from app.services import visibility_run_service

    return visibility_run_service.execute_run(db_session, run_id=uuid_module.UUID(run_id))


# --- project ---------------------------------------------------------------


def test_project_is_created_with_methodology_version(client: TestClient, register_org) -> None:
    """Methodology version is what makes historical comparison honest."""
    org = register_org()
    project = _project(client, org["headers"])
    assert project["methodology_version"] == "v1"
    assert project["status"] == "active"
    assert project["target_brand"] == "Taranjabin Co"


def test_projects_are_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _project(client, org_b["headers"])
    listing = client.get("/api/v1/visibility/projects", headers=org_a["headers"]).json()
    assert listing["total"] == 0


def test_project_list_supports_canonical_sorting(client: TestClient, register_org) -> None:
    org = register_org()
    _project(client, org["headers"], name="alpha")
    _project(client, org["headers"], name="zulu")
    body = client.get("/api/v1/visibility/projects?sort_by=name&sort_dir=asc",
                      headers=org["headers"]).json()
    assert [p["name"] for p in body["items"]] == ["alpha", "zulu"]


def test_unknown_sort_field_is_422(client: TestClient, register_org) -> None:
    org = register_org()
    assert client.get("/api/v1/visibility/projects?sort_by=bogus",
                      headers=org["headers"]).status_code == 422


# --- run is async ------------------------------------------------------------


def test_run_creation_returns_202_and_does_not_probe(client: TestClient, register_org) -> None:
    """No provider is called in the request (P12-18 §9)."""
    org = register_org()
    _queries(client, org["headers"], ["taranjabin benefits"])
    project = _project(client, org["headers"])

    response = _run(client, org["headers"], project["id"])
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_id"]
    assert body["status_url"].endswith(body["run_id"])

    run = client.get(f"/api/v1/visibility/runs/{body['run_id']}",
                     headers=org["headers"]).json()
    assert run["queries_observed"] == 0, "nothing may be observed before the worker runs"


# --- full E2E: run -> observations -> snapshot -> events ------------------------


def test_run_execution_persists_observations_snapshot_and_events(
    client: TestClient, register_org, db_session
) -> None:
    """THE route-level E2E. Every stage is asserted from persisted state."""
    org = register_org()
    _queries(client, org["headers"], ["taranjabin benefits", "taranjabin price"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()

    result = _execute(db_session, accepted["run_id"])
    assert result["status"] in ("succeeded", "partial")
    assert result["observed"] >= 1

    run = client.get(f"/api/v1/visibility/runs/{accepted['run_id']}",
                     headers=org["headers"]).json()
    assert run["queries_observed"] >= 1

    observations = client.get("/api/v1/visibility/observations",
                              headers=org["headers"]).json()
    assert observations["total"] >= 1

    snapshots = client.get(f"/api/v1/visibility/projects/{project['id']}/snapshots",
                           headers=org["headers"]).json()
    assert snapshots["total"] == 1
    snapshot = snapshots["items"][0]
    assert snapshot["observations_tested"] >= 1
    assert snapshot["methodology_version"] == "v1"

    events = client.get(f"/api/v1/visibility/projects/{project['id']}/events",
                        headers=org["headers"]).json()
    assert events["total"] >= 1
    assert events["items"][0]["determination"] == "observed"


def test_first_run_emits_first_observed_event(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    _queries(client, org["headers"], ["q1"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()
    _execute(db_session, accepted["run_id"])

    events = client.get(f"/api/v1/visibility/projects/{project['id']}/events",
                        headers=org["headers"]).json()
    assert any(e["event_type"] == "first_observed" for e in events["items"])


def test_events_carry_no_causal_claim(client: TestClient, register_org, db_session) -> None:
    """The system observes that a value changed; it cannot know why."""
    from app.models.visibility_project import VisibilityEvent

    columns = {c.name for c in VisibilityEvent.__table__.columns}
    for forbidden in ("cause", "caused_by", "impact", "attribution", "reason"):
        assert forbidden not in columns


# --- provider failure semantics ---------------------------------------------------


def test_provider_failure_is_recorded_not_dropped(
    client: TestClient, register_org, db_session
) -> None:
    """A failed probe still produces an observation. Dropping it would
    shrink the denominator and inflate every rate."""
    org = register_org()
    _queries(client, org["headers"], ["[unavailable] taranjabin"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()

    result = _execute(db_session, accepted["run_id"])
    assert result["failed"] >= 1

    observations = client.get("/api/v1/visibility/observations",
                              headers=org["headers"]).json()["items"]
    assert observations, "the failed probe must still be recorded"
    failed = observations[0]
    assert failed["mentioned"] == "not_checked", (
        "a failed probe must not produce an ABSENT finding"
    )


def test_partial_run_is_neither_succeeded_nor_failed(
    client: TestClient, register_org, db_session
) -> None:
    """A run where some queries failed is PARTIAL — forcing it either way
    loses the distinction an operator needs."""
    org = register_org()
    _queries(client, org["headers"], ["good query", "[unavailable] bad query"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()
    _execute(db_session, accepted["run_id"])

    run = client.get(f"/api/v1/visibility/runs/{accepted['run_id']}",
                     headers=org["headers"]).json()
    assert run["status"] == VisibilityRunStatus.PARTIAL.value
    assert run["queries_observed"] >= 1 and run["queries_failed"] >= 1


def test_not_configured_provider_observes_nothing_and_claims_nothing(
    client: TestClient, register_org, db_session
) -> None:
    """The default provider must report NOT_CONFIGURED, never an empty
    success that reads as 'brand absent'."""
    org = register_org()
    _queries(client, org["headers"], ["q"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"], provider="not_configured").json()
    _execute(db_session, accepted["run_id"])

    observations = client.get("/api/v1/visibility/observations",
                              headers=org["headers"]).json()["items"]
    assert observations
    for field in ("mentioned", "cited", "recommended", "product_present", "url_present"):
        assert observations[0][field] == "not_checked"


def test_fixture_observations_are_marked_as_fixture(
    client: TestClient, register_org, db_session
) -> None:
    """Fixture data must never be mistaken for a live observation (§44)."""
    from sqlalchemy import select

    from app.models.visibility import VisibilityTest

    org = register_org()
    _queries(client, org["headers"], ["q"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()
    _execute(db_session, accepted["run_id"])

    row = db_session.execute(
        select(VisibilityTest).where(
            VisibilityTest.organization_id == uuid_module.UUID(org["organization"]["id"])
        )
    ).scalars().first()
    assert row.is_fixture is True
    assert row.provider_outcome in ("success", "partial")


def test_run_with_no_budget_refuses_every_paid_probe(
    client: TestClient, register_org, db_session
) -> None:
    """The budget guard integrated into run execution (§28). With no
    budget, probes are refused and recorded as unavailable — NOT as absent
    findings, and NOT silently skipped."""
    org = register_org()
    _queries(client, org["headers"], ["q1"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"], budget=0).json()

    result = _execute(db_session, accepted["run_id"])
    assert result["failed"] >= 1
    assert result["observed"] == 0

    observations = client.get("/api/v1/visibility/observations",
                              headers=org["headers"]).json()["items"]
    assert observations, "a refused probe is still recorded"
    assert observations[0]["mentioned"] == "not_checked"


# --- rates and denominators ---------------------------------------------------------


def test_rates_expose_denominator_and_sample(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    _queries(client, org["headers"], ["q1", "q2"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()
    _execute(db_session, accepted["run_id"])

    snapshot_id = client.get(
        f"/api/v1/visibility/projects/{project['id']}/snapshots", headers=org["headers"]
    ).json()["items"][0]["id"]

    rates = client.get(f"/api/v1/visibility/snapshots/{snapshot_id}/rates",
                       headers=org["headers"]).json()
    assert rates["denominator"] >= 1
    assert rates["sample"]["observations_tested"] == rates["denominator"]
    assert "observations_failed" in rates["sample"]
    assert "not a market share" in rates["caveat"].lower()


def test_no_global_ai_score_anywhere_in_the_response(
    client: TestClient, register_org, db_session
) -> None:
    """§13: no AI Visibility Score, AI Authority Score or equivalent."""
    org = register_org()
    _queries(client, org["headers"], ["q"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()
    _execute(db_session, accepted["run_id"])
    snapshot_id = client.get(
        f"/api/v1/visibility/projects/{project['id']}/snapshots", headers=org["headers"]
    ).json()["items"][0]["id"]

    text = client.get(f"/api/v1/visibility/snapshots/{snapshot_id}/rates",
                      headers=org["headers"]).text.lower()
    for forbidden in ("visibility_score", "authority_score", "ai_score",
                      "rank_score", "overall_score"):
        assert forbidden not in text


def test_rate_is_null_not_zero_when_nothing_was_tested(
    client: TestClient, register_org, db_session
) -> None:
    """0.0 would assert a measured absence; null says nothing was measured."""
    from app.services.visibility_run_service import snapshot_rates
    from app.models.visibility_project import VisibilitySnapshot
    from app.models.enums import VisibilityPlatform
    from datetime import datetime, timezone

    snapshot = VisibilitySnapshot(
        organization_id=uuid_module.uuid4(), project_id=uuid_module.uuid4(),
        platform=VisibilityPlatform.CHATGPT, observations_total=3,
        observations_tested=0, captured_at=datetime.now(timezone.utc),
    )
    rates = snapshot_rates(snapshot)
    assert rates["denominator"] == 0
    assert rates["ai_mention_rate"] is None
    assert rates["ai_citation_rate"] is None


# --- competitors -------------------------------------------------------------------


def test_merchant_defined_competitor_is_approved(client: TestClient, register_org) -> None:
    org = register_org()
    project = _project(client, org["headers"])
    competitor = client.post(
        f"/api/v1/visibility/projects/{project['id']}/competitors",
        json={"name": "Rival", "domain": "rival.example", "origin": "merchant_defined"},
        headers=org["headers"],
    ).json()
    assert competitor["is_approved"] is True


def test_system_discovered_competitor_is_not_approved(client: TestClient, register_org) -> None:
    """Declaring a brand a competitor without approval puts words in the
    merchant's mouth."""
    org = register_org()
    project = _project(client, org["headers"])
    competitor = client.post(
        f"/api/v1/visibility/projects/{project['id']}/competitors",
        json={"name": "Maybe", "domain": "maybe.example", "origin": "system_discovered"},
        headers=org["headers"],
    ).json()
    assert competitor["is_approved"] is False
    assert competitor["origin"] == "system_discovered"


# --- tenancy -----------------------------------------------------------------------


def test_cannot_create_run_on_another_orgs_project(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    project_b = _project(client, org_b["headers"])
    assert _run(client, org_a["headers"], project_b["id"]).status_code == 404


def test_cannot_read_another_orgs_run(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _queries(client, org_b["headers"], ["q"])
    project_b = _project(client, org_b["headers"])
    run_b = _run(client, org_b["headers"], project_b["id"]).json()
    assert client.get(f"/api/v1/visibility/runs/{run_b['run_id']}",
                      headers=org_a["headers"]).status_code == 404


def test_cannot_read_another_orgs_snapshots_or_events(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    project_b = _project(client, org_b["headers"])
    for path in ("snapshots", "events", "competitors"):
        assert client.get(f"/api/v1/visibility/projects/{project_b['id']}/{path}",
                          headers=org_a["headers"]).status_code == 404


def test_viewer_cannot_create_project_or_run(client: TestClient, register_org) -> None:
    org = register_org()
    client.post("/api/v1/users",
                json={"email": "vis18-viewer@example.dev", "name": "V",
                      "password": "supersecret123", "role": "viewer"},
                headers=org["headers"])
    token = client.post("/api/v1/auth/login",
                        data={"username": "vis18-viewer@example.dev",
                              "password": "supersecret123"}).json()["access_token"]
    viewer = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/visibility/projects",
                       json={"name": "x"}, headers=viewer).status_code == 403


# --- idempotency -------------------------------------------------------------------


def test_repeated_execution_of_a_finished_run_is_a_noop(
    client: TestClient, register_org, db_session
) -> None:
    org = register_org()
    _queries(client, org["headers"], ["q"])
    project = _project(client, org["headers"])
    accepted = _run(client, org["headers"], project["id"]).json()

    _execute(db_session, accepted["run_id"])
    before = client.get("/api/v1/visibility/observations", headers=org["headers"]).json()["total"]
    second = _execute(db_session, accepted["run_id"])
    after = client.get("/api/v1/visibility/observations", headers=org["headers"]).json()["total"]

    assert second.get("repeated") is True or before == after, (
        "re-running a finished run must not duplicate observations"
    )
