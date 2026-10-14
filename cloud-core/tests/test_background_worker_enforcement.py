"""
ADR-095 worker enforcement — the persisted BackgroundTaskPolicy controls what the
worker actually runs. Exercised through `ai_job_service.run_job`, the function the
Celery task `ai_center.run_job` executes, WITHOUT injected adapters: each account's
adapter is built by the production resolver from its own encrypted credential.

The resources are TEST_PROVIDER accounts (deterministic, non-commercial; enabled only
by TEST_PROVIDER_ENABLED=1). This verifies INTERNAL execution, not a commercial provider.
"""
import uuid

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import settings
from app.integrations.llm import test_provider
from app.models.ai_center import AIJob, AIJobItem, AIProviderAccount, AIRoutingDecision, AIWorkingMemory
from app.models.ai_execution import AIExecution
from app.services import ai_job_service

B = "/api/v1/ai-center"


@pytest.fixture(autouse=True)
def _env(monkeypatch, no_background):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setenv("TEST_PROVIDER_ENABLED", "1")
    test_provider.reset_counters()


@pytest.fixture()
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


def _provider(client, h):
    r = client.post(f"{B}/providers", headers=h, json={"name": f"TEST_PROVIDER {uuid.uuid4().hex[:4]}",
                                                        "adapter_key": "test_provider"})
    assert r.status_code == 201, r.text
    return r.json()


def _account(client, h, pid, label, script, enabled=True):
    a = client.post(f"{B}/accounts", headers=h, json={"provider_id": pid, "label": label}).json()
    # the script is a TEST credential, encrypted exactly like a real one
    assert client.put(f"{B}/accounts/{a['id']}/credential", headers=h,
                      json={"secret": f"{script}#{uuid.uuid4().hex[:6]}"}).status_code == 200
    if not enabled:
        assert client.patch(f"{B}/accounts/{a['id']}", headers=h, json={"enabled": False}).status_code == 200
    return a


def _policy(client, h, mode, accounts):
    r = client.post(f"{B}/routing-policies", headers=h, json={
        "name": f"p-{uuid.uuid4().hex[:6]}", "mode": mode,
        "steps": [{"account_id": a["id"], "model": "test-model"} for a in accounts]})
    assert r.status_code == 201, r.text
    return r.json()


def _bg(client, h, task_type, allowed, enabled=True):
    r = client.put(f"/api/v1/agent-network/background-policies/{task_type}", headers=h,
                   json={"enabled": enabled, "allowed_account_ids": [a["id"] for a in allowed]})
    assert r.status_code == 200, r.text


def _job(client, h, pol, n, task_type="document_processing"):
    r = client.post(f"{B}/jobs", headers=h, json={
        "job_key": f"bg-{uuid.uuid4().hex[:8]}", "goal": "process documents", "policy_id": pol["id"],
        "task_type": task_type, "items": [{"key": f"doc-{i:03d}", "prompt": f"summarise document {i}"} for i in range(n)]})
    assert r.status_code == 202, r.text
    return r.json()


def _run(db, job_view):
    job = db.get(AIJob, uuid.UUID(job_view["id"]))
    return ai_job_service.run_job(db, job)          # no adapters= : production resolution


def _execs(db, account):
    return db.execute(select(func.count()).select_from(AIExecution).where(
        AIExecution.provider_account_id == uuid.UUID(account["id"]))).scalar_one()


def test_connected_but_not_allowed_is_never_selected(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A-connected-not-allowed", "test:ok")
    b = _account(client, h, p["id"], "B-allowed", "test:ok")
    pol = _policy(client, h, "manual_chain", [a, b])          # A is FIRST in the user's chain
    _bg(client, h, "document_processing", [b])                 # but only B may do background work
    res = _run(db_session, _job(client, h, pol, 5))
    assert res["status"] == "completed" and res["completed"] == 5
    assert _execs(db_session, a) == 0                          # A never invoked
    assert _execs(db_session, b) == 5                          # one execution per real invocation
    dec = db_session.execute(select(AIRoutingDecision).where(
        AIRoutingDecision.organization_id == uuid.UUID(str(org["organization"]["id"])))).scalars().first()
    reasons = {e["account"]: (e["verdict"], e["reason"]) for e in dec.explanation}
    assert reasons["A-connected-not-allowed"][0] == "skipped"
    assert "not allowed for background processing" in reasons["A-connected-not-allowed"][1]


def test_no_policy_blocks_background_job_and_runs_nothing(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_chain", [a]), 3))
    assert res["status"] == "blocked" and res["stop_reason"] == "POLICY_MISSING"
    assert _execs(db_session, a) == 0


def test_disabled_policy_blocks(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    _bg(client, h, "document_processing", [a], enabled=False)
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_chain", [a]), 2))
    assert res["stop_reason"] == "POLICY_DISABLED" and _execs(db_session, a) == 0


def test_allowed_but_disabled_account_is_skipped(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A-disabled", "test:ok", enabled=False)
    b = _account(client, h, p["id"], "B", "test:ok")
    _bg(client, h, "document_processing", [a, b])
    res = _run(db_session, _job(client, h, _policy(client, h, "priority_pool", [a, b]), 3))
    assert res["completed"] == 3 and _execs(db_session, a) == 0 and _execs(db_session, b) == 3


@pytest.mark.parametrize("script,stop", [("test:rate_limit_after:2", "RATE_LIMIT"),
                                         ("test:quota_after:2", "QUOTA_EXHAUSTED"),
                                         ("test:auth_fail", "AUTHENTICATION_FAILED")])
def test_failure_switches_with_checkpoint_and_never_reprocesses(client, db_session, register_org, script, stop):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", script)
    b = _account(client, h, p["id"], "B", "test:ok")
    _bg(client, h, "document_processing", [a, b])
    jv = _job(client, h, _policy(client, h, "manual_chain", [a, b]), 6)
    res = _run(db_session, jv)
    assert res["status"] == "completed" and res["completed"] == 6
    job = db_session.get(AIJob, uuid.UUID(jv["id"]))
    items = db_session.execute(select(AIJobItem).where(AIJobItem.job_id == job.id)).scalars().all()
    done_by = {str(i.completed_by_account_id) for i in items}
    assert all(i.status == "completed" for i in items)
    # every item completed exactly once: successful executions == items
    ok = db_session.execute(select(func.count()).select_from(AIExecution).where(
        AIExecution.ai_job_id == job.id, AIExecution.status == "succeeded")).scalar_one()
    assert ok == 6
    stopped = db_session.execute(select(AIExecution).where(AIExecution.ai_job_id == job.id,
                                 AIExecution.stop_reason == stop)).scalars().all()
    assert len(stopped) == 1                                   # the failing call is its own execution
    kinds = {m.kind for m in db_session.execute(select(AIWorkingMemory).where(
        AIWorkingMemory.job_key == job.job_key)).scalars()}
    assert {"processing_checkpoint", "ai_handoff"} <= kinds     # persisted BEFORE the switch
    assert b["id"] in done_by


def test_all_candidates_unavailable_is_a_truthful_block(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:auth_fail")
    b = _account(client, h, p["id"], "B", "test:auth_fail")
    _bg(client, h, "document_processing", [a, b])
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_chain", [a, b]), 3))
    assert res["status"] == "blocked" and res["completed"] == 0 and res["stop_reason"]


def test_manual_single_is_not_overridden_by_automatic_fallback(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:rate_limit_after:1")
    b = _account(client, h, p["id"], "B", "test:ok")
    _bg(client, h, "document_processing", [a, b])
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_single", [a]), 3))
    assert res["status"] == "blocked" and res["completed"] == 1
    assert _execs(db_session, b) == 0                          # user chose A only


def test_manual_switch_to_forbidden_account_is_refused(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    c = _account(client, h, p["id"], "C-forbidden", "test:ok")
    _bg(client, h, "document_processing", [a])
    jv = _job(client, h, _policy(client, h, "manual_chain", [a, c]), 3)
    job = db_session.get(AIJob, uuid.UUID(jv["id"]))
    job.forced_account_id = uuid.UUID(c["id"]); db_session.commit()
    res = _run(db_session, jv)
    assert res["completed"] == 3 and _execs(db_session, c) == 0


def test_interactive_job_without_task_type_keeps_previous_behaviour(client, db_session, register_org):
    """A job the user starts with an explicit routing policy (no task_type) is not background work."""
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    jv = _job(client, h, _policy(client, h, "manual_single", [a]), 2, task_type=None)
    assert _run(db_session, jv)["completed"] == 2


def test_test_provider_is_unavailable_without_the_flag(client, db_session, register_org, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_ENABLED", "0")
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    _bg(client, h, "document_processing", [a])
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_chain", [a]), 2))
    assert res["status"] == "blocked" and _execs(db_session, a) == 0


def test_background_cost_limit_stops_before_spending(client, db_session, register_org):
    """Background policy max cost: TEST_PROVIDER has no known price, so under a cost cap the
    worker must stop BEFORE the call (unknown price is never treated as free)."""
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    r = client.put("/api/v1/agent-network/background-policies/document_processing", headers=h,
                   json={"enabled": True, "allowed_account_ids": [a["id"]], "max_cost_per_run": 0.01})
    assert r.status_code == 200
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_chain", [a]), 2))
    assert res["status"] == "blocked" and res["stop_reason"] == "SPEND_LIMIT"
    assert _execs(db_session, a) == 0


def test_background_routing_policy_overrides_the_job_policy(client, db_session, register_org):
    org = register_org(); h = org["headers"]; p = _provider(client, h)
    a = _account(client, h, p["id"], "A", "test:ok")
    b = _account(client, h, p["id"], "B", "test:ok")
    bg_pol = _policy(client, h, "manual_single", [b])
    r = client.put("/api/v1/agent-network/background-policies/document_processing", headers=h,
                   json={"enabled": True, "allowed_account_ids": [a["id"], b["id"]], "routing_policy_id": bg_pol["id"]})
    assert r.status_code == 200
    res = _run(db_session, _job(client, h, _policy(client, h, "manual_single", [a]), 2))
    assert res["completed"] == 2 and _execs(db_session, a) == 0 and _execs(db_session, b) == 2
