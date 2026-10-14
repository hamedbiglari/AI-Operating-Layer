"""
Agent A → Agent B end-to-end through the public API and the real execution path
(agent task → AI job → AIExecution via production adapter resolution). Resources are
TEST_PROVIDER accounts: INTERNAL EXECUTION VERIFIED, not a commercial provider.
"""
import uuid

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.integrations.llm import test_provider
from app.models.agent_network import AgentMessage, AgentTask
from app.models.ai_execution import AIExecution
from app.models.audit_log import AuditLog

N = "/api/v1/agent-network"
C = "/api/v1/ai-center"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setenv("TEST_PROVIDER_ENABLED", "1")
    test_provider.reset_counters()


def _ok(r, codes=(200, 201)):
    assert r.status_code in codes, f"{r.status_code} {r.text[:300]}"
    return r.json()


def _world(client, org, script_a="test:ok", script_b="test:ok"):
    h = org["headers"]
    p = _ok(client.post(f"{C}/providers", headers=h, json={"name": f"TEST_PROVIDER {uuid.uuid4().hex[:4]}",
                                                           "adapter_key": "test_provider"}))
    accts = []
    for label, script in (("acct-A", script_a), ("acct-B", script_b)):
        a = _ok(client.post(f"{C}/accounts", headers=h, json={"provider_id": p["id"], "label": label}))
        _ok(client.put(f"{C}/accounts/{a['id']}/credential", headers=h, json={"secret": f"{script}#{uuid.uuid4().hex[:6]}"}))
        accts.append(a)
    pol = _ok(client.post(f"{C}/routing-policies", headers=h, json={
        "name": f"p-{uuid.uuid4().hex[:6]}", "mode": "manual_chain",
        "steps": [{"account_id": a["id"], "model": "test-model"} for a in accts]}))
    mem = _ok(client.post(f"{N}/memory-profiles", headers=h, json={"name": f"Research Memory {uuid.uuid4().hex[:4]}"}))
    ra = _ok(client.post(f"{N}/agents", headers=h, json={"name": "Research Agent", "agent_type": "research",
             "capabilities": ["research"], "allowed_ai_accounts": [accts[0]["id"]]}))
    ev = _ok(client.post(f"{N}/agents", headers=h, json={"name": "Evidence Agent", "agent_type": "evidence",
             "capabilities": ["evidence_analysis"], "allowed_ai_accounts": [accts[1]["id"]]}))
    for ag in (ra, ev):
        _ok(client.put(f"{N}/agents/{ag['id']}/memory-bindings", headers=h,
                       json={"memory_profile_id": mem["id"], "access_level": "write"}))
    s = _ok(client.post(f"{N}/sessions", headers=h, json={"session_key": f"s-{uuid.uuid4().hex[:6]}",
             "goal": "Analyze source X", "memory_profile_id": mem["id"]}))
    return {"h": h, "accts": accts, "pol": pol, "mem": mem, "ra": ra, "ev": ev, "s": s}


def test_research_agent_hands_off_to_evidence_agent(client, db_session, register_org):
    w = _world(client, register_org()); h, s = w["h"], w["s"]
    t1 = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "research", "task_key": "analyze-x"}))
    assert t1["status"] == "created"
    r1 = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t1['id']}/run", headers=h, json={
        "agent_id": w["ra"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "Analyze source X"}))
    assert r1["status"] == "completed" and len(r1["ai_execution_ids"]) == 1
    # the Research Agent may only use acct-A: its execution is attributed to acct-A
    e1 = db_session.get(AIExecution, uuid.UUID(r1["ai_execution_ids"][0]))
    assert str(e1.provider_account_id) == w["accts"][0]["id"] and e1.status == "succeeded" and e1.provider == "test_provider"
    ho = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t1['id']}/handoff", headers=h,
                         json={"from_agent_id": w["ra"]["id"], "to_agent_id": w["ev"]["id"]}))
    assert ho["working_memory_id"]                              # shared-memory checkpoint persisted
    _ok(client.post(f"{N}/handoffs/{ho['id']}/accept", headers=h, json={"agent_id": w["ev"]["id"]}))
    t2 = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "evidence_analysis", "task_key": "evidence-x"}))
    r2 = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t2['id']}/run", headers=h, json={
        "agent_id": w["ev"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "Extract evidence",
        "handoff_id": ho["id"]}))
    assert r2["status"] == "completed" and r2["findings"]["previous"] is not None
    e2 = db_session.get(AIExecution, uuid.UUID(r2["ai_execution_ids"][0]))
    assert str(e2.provider_account_id) == w["accts"][1]["id"]  # Evidence Agent used ITS resource
    assert e1.id != e2.id                                        # separate invocations, separate executions
    # audit trail: durable handoff message acknowledged
    msgs = _ok(client.get(f"{N}/sessions/{s['id']}/messages", headers=h))
    assert msgs[0]["type"] == "handoff" and msgs[0]["acknowledged_at"] is not None
    handoffs = _ok(client.get(f"{N}/sessions/{s['id']}/handoffs", headers=h))
    assert handoffs[0]["status"] == "accepted"
    tasks = {t["task_key"]: t for t in _ok(client.get(f"{N}/sessions/{s['id']}/tasks", headers=h))}
    assert tasks["analyze-x"]["status"] == "completed" and tasks["evidence-x"]["status"] == "completed"


def test_handoff_package_references_memory_not_copies(client, db_session, register_org):
    w = _world(client, register_org()); h, s = w["h"], w["s"]
    t1 = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "research", "task_key": "k"}))
    _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t1['id']}/run", headers=h, json={
        "agent_id": w["ra"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "p"}))
    ho = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t1['id']}/handoff", headers=h,
                         json={"from_agent_id": w["ra"]["id"], "to_agent_id": w["ev"]["id"], "reason": "stage_complete"}))
    from app.models.agent_network import AgentHandoff
    pkg = db_session.get(AgentHandoff, uuid.UUID(str(ho["id"]))).package
    for f in ("task_id", "goal", "completed_work", "findings", "evidence_refs", "open_questions", "conflicts",
              "next_actions", "previous_ai_execution_ids", "to_agent_id", "memory_profile_id"):
        assert f in pkg, f
    assert len(pkg["previous_ai_execution_ids"]) == 1


def test_agent_without_memory_binding_is_denied_and_audited(client, db_session, register_org):
    org = register_org(); w = _world(client, org); h, s = w["h"], w["s"]
    outsider = _ok(client.post(f"{N}/agents", headers=h, json={"name": "Unbound Agent", "agent_type": "content",
                   "allowed_ai_accounts": [w["accts"][0]["id"]]}))
    t = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "content", "task_key": "c"}))
    r = client.post(f"{N}/sessions/{s['id']}/tasks/{t['id']}/run", headers=h, json={
        "agent_id": outsider["id"], "routing_policy_id": w["pol"]["id"], "prompt": "p"})
    assert r.status_code == 403
    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "agent.memory_access_denied",
                               AuditLog.resource_id == uuid.UUID(w["mem"]["id"]))).scalars().all()
    assert audit, "memory denial must leave an audit event"
    assert db_session.execute(select(AIExecution).where(AIExecution.organization_id ==
                              uuid.UUID(str(org["organization"]["id"])))).scalars().first() is None


def test_only_the_addressed_agent_can_accept(client, register_org):
    w = _world(client, register_org()); h, s = w["h"], w["s"]
    t = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "research", "task_key": "k"}))
    _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t['id']}/run", headers=h, json={
        "agent_id": w["ra"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "p"}))
    ho = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t['id']}/handoff", headers=h,
                         json={"from_agent_id": w["ra"]["id"], "to_agent_id": w["ev"]["id"]}))
    r = client.post(f"{N}/handoffs/{ho['id']}/accept", headers=h, json={"agent_id": w["ra"]["id"]})
    assert r.status_code == 409


def test_agent_cannot_use_ai_resources_it_does_not_declare(client, db_session, register_org):
    """Research Agent declares only acct-A; acct-A fails auth → it must NOT fall back to acct-B."""
    w = _world(client, register_org(), script_a="test:auth_fail"); h, s = w["h"], w["s"]
    t = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "research", "task_key": "k"}))
    r = _ok(client.post(f"{N}/sessions/{s['id']}/tasks/{t['id']}/run", headers=h, json={
        "agent_id": w["ra"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "p"}))
    assert r["status"] == "blocked"
    used = {str(db_session.get(AIExecution, uuid.UUID(i)).provider_account_id) for i in r["ai_execution_ids"]}
    assert used == {w["accts"][0]["id"]}


def test_lifecycle_rejects_illegal_transitions(client, db_session, register_org):
    from app.services.agent_execution_service import AgentExecutionService, IllegalTransition
    org = register_org(); w = _world(client, org); h, s = w["h"], w["s"]
    t = _ok(client.post(f"{N}/sessions/{s['id']}/tasks", headers=h, json={"task_type": "research", "task_key": "k"}))
    task = db_session.get(AgentTask, uuid.UUID(str(t["id"])))
    svc = AgentExecutionService(db_session, uuid.UUID(str(org["organization"]["id"])))
    with pytest.raises(IllegalTransition):
        svc.transition(task, "completed")                       # created → completed is not allowed
    svc.queue(task); svc.cancel(task)
    assert task.status == "cancelled"
    with pytest.raises(IllegalTransition):
        svc.transition(task, "running")                         # terminal


def test_cross_tenant_agent_access_is_404(client, register_org):
    a = register_org(); b = register_org(); w = _world(client, a)
    s, t_ = w["s"], _ok(client.post(f"{N}/sessions/{w['s']['id']}/tasks", headers=w["h"],
                                      json={"task_type": "research", "task_key": "k"}))
    hb = b["headers"]
    assert client.get(f"{N}/agents/{w['ra']['id']}", headers=hb).status_code == 404
    assert client.get(f"{N}/sessions/{s['id']}/tasks", headers=hb).status_code == 404
    assert client.get(f"{N}/sessions/{s['id']}/messages", headers=hb).status_code == 404
    r = client.post(f"{N}/sessions/{s['id']}/tasks/{t_['id']}/run", headers=hb, json={
        "agent_id": w["ra"]["id"], "routing_policy_id": w["pol"]["id"], "prompt": "p"})
    assert r.status_code == 404
    assert client.put(f"{N}/agents/{w['ra']['id']}/memory-bindings", headers=hb,
                      json={"memory_profile_id": w["mem"]["id"]}).status_code == 404


def test_agent_endpoint_ssrf_is_blocked(client, register_org):
    h = register_org()["headers"]
    for url in ("http://127.0.0.1:8000/x", "http://169.254.169.254/latest", "http://10.0.0.8/a", "http://user:pw@example.com/"):
        r = client.post(f"{N}/agents", headers=h, json={"name": f"ext-{uuid.uuid4().hex[:4]}", "agent_type": "external",
                        "protocol": "rest", "endpoint_url": url})
        assert r.status_code == 422, url
